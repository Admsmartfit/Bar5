"""Importação do extrato da maquininha (CSV/XLSX) e do banco (OFX) e casamento com os recebíveis."""

import base64
import csv
import io
import re
import unicodedata
from datetime import datetime, timedelta

from odoo import _, api, fields, models
from odoo.exceptions import UserError

from .conciliacao import TOLERANCIA_TAXA_PP

# Cabeçalhos mais comuns nos extratos das maquininhas (sem acento, minúsculo)
SINONIMOS = {
    "data": ["data da venda", "data venda", "data da transacao", "data transacao", "data/hora", "data e hora", "data"],
    "bruto": ["valor bruto", "valor da venda", "valor bruto da venda", "valor original", "valor da transacao", "bruto", "valor"],
    "liquido": ["valor liquido", "valor liquido da venda", "valor a receber", "liquido"],
    "taxa": ["valor da taxa", "taxa", "desconto", "mdr", "tarifa", "taxas"],
    "nsu": ["nsu", "stone id", "codigo da venda", "cv", "id da transacao", "codigo de autorizacao", "autorizacao"],
    "bandeira": ["bandeira"],
    "modalidade": ["produto", "modalidade", "forma de pagamento", "meio de pagamento", "tipo de transacao", "tipo"],
    "parcelas": ["qtd parcelas", "numero de parcelas", "parcelas", "n parcelas"],
    "previsao": ["previsao de pagamento", "data de pagamento", "data prevista", "data do repasse", "vencimento"],
    "status": ["status", "situacao"],
}


def normalizar(texto):
    texto = unicodedata.normalize("NFKD", str(texto or "")).encode("ascii", "ignore").decode()
    return re.sub(r"\s+", " ", texto).strip().lower()


def numero(valor):
    """'1.234,56' / '1234.56' / 'R$ -12,30' / 12.3 -> float."""
    if isinstance(valor, (int, float)):
        return float(valor)
    texto = re.sub(r"[^\d,.\-]", "", str(valor or ""))
    if not texto:
        return 0.0
    if "," in texto and "." in texto:
        texto = texto.replace(".", "").replace(",", ".") if texto.rfind(",") > texto.rfind(".") else texto.replace(",", "")
    elif "," in texto:
        texto = texto.replace(",", ".")
    try:
        return float(texto)
    except ValueError:
        return 0.0


def data(valor):
    if isinstance(valor, datetime):
        return valor.date()
    if hasattr(valor, "year") and not isinstance(valor, str):
        return valor
    texto = str(valor or "").strip()
    for formato in ("%d/%m/%Y %H:%M:%S", "%d/%m/%Y %H:%M", "%d/%m/%Y", "%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S",
                    "%Y-%m-%d", "%d-%m-%Y", "%d/%m/%y"):
        try:
            return datetime.strptime(texto[:len(datetime.now().strftime(formato))], formato).date()
        except ValueError:
            continue
    return None


def ler_planilha(conteudo, nome):
    """Linhas (lista de listas) de CSV (; ou ,) ou XLSX."""
    if (nome or "").lower().endswith((".xlsx", ".xlsm")):
        from openpyxl import load_workbook
        planilha = load_workbook(io.BytesIO(conteudo), read_only=True, data_only=True).active
        return [list(linha) for linha in planilha.iter_rows(values_only=True)]
    for codificacao in ("utf-8-sig", "latin-1"):
        try:
            texto = conteudo.decode(codificacao)
            break
        except UnicodeDecodeError:
            continue
    amostra = texto[:4096]
    separador = ";" if amostra.count(";") >= amostra.count(",") else ","
    return list(csv.reader(io.StringIO(texto), delimiter=separador))


def ler_ofx(conteudo):
    texto = conteudo.decode("latin-1")
    transacoes = []
    for bloco in re.findall(r"<STMTTRN>(.*?)(?:</STMTTRN>|(?=<STMTTRN>)|</BANKTRANLIST>)", texto, re.S | re.I):
        def campo(nome):
            achado = re.search(r"<%s>([^<\r\n]*)" % nome, bloco, re.I)
            return achado.group(1).strip() if achado else ""
        quando = campo("DTPOSTED")[:8]
        transacoes.append({
            "data": datetime.strptime(quando, "%Y%m%d").date() if len(quando) == 8 else None,
            "valor": numero(campo("TRNAMT")),
            "id": campo("FITID"), "descricao": campo("MEMO") or campo("NAME"),
        })
    return transacoes


class BotecoExtrato(models.Model):
    _name = "boteco.extrato"
    _description = "Extrato importado (maquininha ou banco)"
    _order = "create_date desc, id desc"

    name = fields.Char("Descrição", compute="_compute_name", store=True)
    tipo = fields.Selection([("maquininha", "Extrato da maquininha (CSV/XLSX)"), ("banco", "Extrato do banco (OFX)")],
                            required=True, default="maquininha")
    adquirente_id = fields.Many2one("boteco.adquirente", string="Maquininha")
    arquivo = fields.Binary("Arquivo", required=True, attachment=True)
    arquivo_nome = fields.Char("Nome do arquivo")
    linha_ids = fields.One2many("boteco.extrato.linha", "extrato_id", string="Linhas")
    estado = fields.Selection([("novo", "Novo"), ("importado", "Importado")], default="novo", required=True)
    n_casadas = fields.Integer("Casadas", compute="_compute_resumo")
    n_conferir = fields.Integer("Para conferir", compute="_compute_resumo")
    company_id = fields.Many2one("res.company", required=True, default=lambda s: s.env.company)

    @api.depends("tipo", "adquirente_id", "arquivo_nome", "create_date")
    def _compute_name(self):
        for e in self:
            origem = e.adquirente_id.name if e.tipo == "maquininha" else _("Banco")
            e.name = "%s – %s" % (origem or "", e.arquivo_nome or "")

    @api.depends("linha_ids.estado")
    def _compute_resumo(self):
        for e in self:
            e.n_casadas = len(e.linha_ids.filtered(lambda l: l.estado == "casado"))
            e.n_conferir = len(e.linha_ids.filtered(lambda l: l.estado == "conferir"))

    # ------------------------------------------------------------------ importar
    def action_importar(self):
        for extrato in self:
            if not extrato.company_id.boteco_recurso_ativo("conciliacao_cartoes"):
                raise UserError(_("A conferência de cartões e Pix está desligada na Central de Recursos."))
            conteudo = base64.b64decode(extrato.arquivo or b"")
            extrato.linha_ids.unlink()
            if extrato.tipo == "banco":
                extrato._importar_ofx(conteudo)
            else:
                if not extrato.adquirente_id:
                    raise UserError(_("Escolha de qual maquininha é o extrato."))
                extrato._importar_maquininha(conteudo)
            extrato.estado = "importado"
        return True

    def _colunas(self, cabecalho):
        """Posição de cada campo: primeiro o que está no cadastro da maquininha, depois os nomes mais comuns."""
        nomes = [normalizar(c) for c in cabecalho]
        posicoes = {}
        for campo, sinonimos in SINONIMOS.items():
            configurado = normalizar(getattr(self.adquirente_id, "coluna_%s" % campo, "") or "")
            candidatos = [configurado] if configurado else sinonimos
            for candidato in candidatos:
                if candidato in nomes and nomes.index(candidato) not in posicoes.values():
                    posicoes[campo] = nomes.index(candidato)
                    break
        return posicoes

    def _importar_maquininha(self, conteudo):
        linhas = [l for l in ler_planilha(conteudo, self.arquivo_nome) if any(str(c or "").strip() for c in l)]
        inicio = next((i for i, l in enumerate(linhas[:15]) if len(self._colunas(l)) >= 2
                       and {"data", "bruto"} <= set(self._colunas(l))), None)
        if inicio is None:
            raise UserError(_("Não achei as colunas de data e valor da venda. Informe os nomes das colunas no cadastro "
                              "da maquininha (Cartões e Pix › Maquininhas)."))
        pos = self._colunas(linhas[inicio])
        Linha = self.env["boteco.extrato.linha"]
        vals = []
        for bruta in linhas[inicio + 1:]:
            def valor(campo):
                i = pos.get(campo)
                return bruta[i] if i is not None and i < len(bruta) else None
            quando = data(valor("data"))
            bruto = numero(valor("bruto"))
            if not quando or not bruto:
                continue
            liquido = numero(valor("liquido")) if valor("liquido") is not None else 0.0
            taxa = abs(numero(valor("taxa"))) if valor("taxa") is not None else 0.0
            if not taxa and liquido:
                taxa = round(abs(bruto) - abs(liquido), 2)
            status = normalizar(valor("status"))
            estorno = bruto < 0 or any(p in status for p in ("estorn", "cancel", "chargeback", "contestac"))
            vals.append({
                "extrato_id": self.id, "tipo_linha": "estorno" if estorno else "venda", "data": quando,
                "data_pagamento": data(valor("previsao")), "valor_bruto": abs(bruto),
                "valor_liquido": abs(liquido) or round(abs(bruto) - taxa, 2), "taxa_valor": taxa,
                "nsu": str(valor("nsu") or "").strip() or False, "bandeira": str(valor("bandeira") or "").strip() or False,
                "modalidade_texto": str(valor("modalidade") or "").strip() or False,
                "parcelas": int(numero(valor("parcelas")) or 1),
            })
        novas = Linha.create(vals)
        novas._casar_maquininha(self.adquirente_id)

    def _importar_ofx(self, conteudo):
        transacoes = ler_ofx(conteudo)
        if not transacoes:
            raise UserError(_("Arquivo OFX sem lançamentos. Exporte o extrato do banco no formato OFX (Money)."))
        novas = self.env["boteco.extrato.linha"].create([{
            "extrato_id": self.id, "tipo_linha": "credito" if t["valor"] > 0 else "debito", "data": t["data"],
            "valor_bruto": abs(t["valor"]), "valor_liquido": abs(t["valor"]), "nsu": t["id"] or False,
            "descricao": t["descricao"] or False,
        } for t in transacoes if t["data"] and t["valor"]])
        novas._casar_banco()


class BotecoExtratoLinha(models.Model):
    _name = "boteco.extrato.linha"
    _description = "Linha do extrato"
    _order = "data, id"

    extrato_id = fields.Many2one("boteco.extrato", required=True, ondelete="cascade", index=True)
    tipo_linha = fields.Selection([("venda", "Venda"), ("estorno", "Estorno / chargeback"), ("credito", "Crédito no banco"),
                                   ("debito", "Débito no banco")], required=True)
    data = fields.Date("Data", required=True)
    data_pagamento = fields.Date("Previsão de pagamento")
    valor_bruto = fields.Float("Valor", digits="Product Price")
    valor_liquido = fields.Float("Líquido", digits="Product Price")
    taxa_valor = fields.Float("Taxa (R$)", digits="Product Price")
    nsu = fields.Char("NSU / identificador")
    bandeira = fields.Char()
    modalidade_texto = fields.Char("Produto")
    parcelas = fields.Integer(default=1)
    descricao = fields.Char("Descrição")
    estado = fields.Selection([("casado", "Casou"), ("conferir", "Conferir"), ("ignorado", "Ignorado")],
                              default="conferir", required=True, index=True)
    motivo = fields.Char("O que conferir")
    recebivel_ids = fields.One2many("boteco.recebivel", "extrato_linha_id", string="Recebíveis")
    company_id = fields.Many2one(related="extrato_id.company_id", store=True)

    def action_ignorar(self):
        self.write({"estado": "ignorado"})

    # ------------------------------------------------------------------ maquininha
    def _casar_maquininha(self, adquirente):
        Recebivel = self.env["boteco.recebivel"].sudo()
        usados = Recebivel.browse()
        for linha in self.sorted(lambda l: (l.tipo_linha != "venda", l.id)):
            base = [("adquirente_id", "=", adquirente.id), ("data_venda", "=", linha.data),
                    ("valor_bruto", ">=", linha.valor_bruto - 0.01), ("valor_bruto", "<=", linha.valor_bruto + 0.01)]
            if linha.tipo_linha == "estorno":
                alvo = Recebivel.search(base + [("estado", "!=", "estornado")], limit=1)
                if linha.nsu:
                    alvo = Recebivel.search([("adquirente_id", "=", adquirente.id), ("nsu", "=", linha.nsu)], limit=1) or alvo
                if alvo:
                    alvo.write({"estado": "estornado", "alerta": _("Estorno/chargeback no extrato da maquininha.")})
                    linha.write({"estado": "casado", "motivo": _("Estorno da venda %s", alvo.order_id.name or "")})
                else:
                    linha.write({"estado": "conferir", "motivo": _("Estorno sem venda correspondente no caixa.")})
                continue
            candidatos = Recebivel.search(base + [("estado", "in", ("previsto", "atrasado")),
                                                  ("extrato_linha_id", "=", False), ("id", "not in", usados.ids)])
            alvo = (linha.nsu and candidatos.filtered(lambda r: r.nsu == linha.nsu)[:1]) or candidatos[:1]
            if not alvo:
                linha.write({"estado": "conferir", "motivo": _("Venda na maquininha sem registro no caixa.")})
                continue
            usados |= alvo
            linha._aplicar_em(alvo)
        # Venda do caixa que não está no extrato (nos dias que o arquivo cobre)
        datas = self.filtered(lambda l: l.tipo_linha == "venda").mapped("data")
        if datas:
            faltando = Recebivel.search([("adquirente_id", "=", adquirente.id), ("estado", "=", "previsto"),
                                         ("extrato_linha_id", "=", False),
                                         ("data_venda", ">=", min(datas)), ("data_venda", "<=", max(datas))])
            faltando.write({"estado": "divergente", "alerta": _("Venda no caixa sem registro na maquininha.")})

    def _aplicar_em(self, recebivel):
        """Casou: confere a taxa cobrada com a contratada."""
        self.ensure_one()
        cobrada = round(self.taxa_valor, 2)
        pct = round(cobrada * 100.0 / self.valor_bruto, 2) if self.valor_bruto else 0.0
        vals = {"extrato_linha_id": self.id, "taxa_cobrada": cobrada, "taxa_cobrada_pct": pct,
                "nsu": recebivel.nsu or self.nsu, "estado": "conferido", "alerta": False, "valor_perdido": 0.0}
        if self.data_pagamento:
            vals["data_prevista"] = self.data_pagamento
        if pct > recebivel.taxa_esperada_pct + TOLERANCIA_TAXA_PP:
            perdido = round(cobrada - recebivel.valor_bruto * recebivel.taxa_esperada_pct / 100.0, 2)
            vals.update(estado="divergente", valor_perdido=perdido,
                        alerta=_("Taxa cobrada %(c).2f%% acima da contratada %(e).2f%%: R$ %(v).2f a mais.",
                                 c=pct, e=recebivel.taxa_esperada_pct, v=perdido))
        recebivel.write(vals)
        self.write({"estado": "casado", "motivo": vals.get("alerta") or False})

    # ------------------------------------------------------------------ banco
    def _casar_banco(self):
        Recebivel = self.env["boteco.recebivel"].sudo()
        abertos = ("previsto", "conferido", "divergente", "atrasado")
        for linha in self:
            if linha.tipo_linha != "credito":
                linha.estado = "ignorado"
                continue
            # 1) Pix do caixa: mesmo valor, no dia ou no dia seguinte
            pix = Recebivel.search([("modalidade", "=", "pix"), ("estado", "in", abertos),
                                    ("data_venda", ">=", linha.data - timedelta(days=1)), ("data_venda", "<=", linha.data),
                                    ("valor_bruto", ">=", linha.valor_bruto - 0.01),
                                    ("valor_bruto", "<=", linha.valor_bruto + 0.01)], limit=1)
            if pix:
                pix.write({"estado": "pago", "alerta": False, "extrato_linha_id": pix.extrato_linha_id.id or linha.id})
                linha.write({"estado": "casado", "motivo": _("Pix da conta %s", pix.order_id.name or "")})
                continue
            # 2) Repasse da maquininha: a soma do que estava previsto para cair nesse dia (até 3 dias antes)
            previstos = Recebivel.search([("modalidade", "!=", "pix"), ("estado", "in", abertos),
                                          ("data_prevista", ">=", linha.data - timedelta(days=3)),
                                          ("data_prevista", "<=", linha.data)])
            casou = False
            for adquirente in previstos.adquirente_id:
                for dia in sorted(set(previstos.filtered(lambda r: r.adquirente_id == adquirente).mapped("data_prevista"))):
                    grupo = previstos.filtered(lambda r: r.adquirente_id == adquirente and r.data_prevista == dia)
                    if abs(sum(r._liquido_real() for r in grupo) - linha.valor_bruto) <= 0.05:
                        for r in grupo:
                            r.write({"estado": "pago" if r.estado != "divergente" else "divergente",
                                     "alerta": r.alerta if r.estado == "divergente" else False})
                        linha.write({"estado": "casado", "motivo": _("Repasse %(a)s de %(d)s",
                                                                    a=adquirente.name, d=dia.strftime("%d/%m"))})
                        casou = True
                        break
                if casou:
                    break
            if not casou:
                linha.write({"estado": "conferir", "motivo": _("Crédito no banco sem venda ou repasse correspondente.")})
