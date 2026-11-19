"""Leitor de orçamento do fornecedor: PDF ou texto colado (Etapa 18). Fotos e WhatsApp: serviço externo."""

import base64
import logging
import re

from odoo import _, api, fields, models
from odoo.exceptions import UserError

from ..tools import orcamento

_logger = logging.getLogger(__name__)



class BotecoImportarOrcamento(models.TransientModel):
    _name = "boteco.importar.orcamento"
    _description = "Ler orçamento de fornecedor (PDF ou texto)"

    partner_id = fields.Many2one("res.partner", string="Fornecedor", required=True)
    arquivo = fields.Binary("PDF")
    nome_arquivo = fields.Char()
    texto = fields.Text("Ou cole o texto", help="Ex.: a lista de preços que o fornecedor mandou no WhatsApp.")
    data = fields.Date("Data da cotação", default=fields.Date.context_today, required=True)
    origem = fields.Selection([("orcamento_pdf", "PDF"), ("orcamento_texto", "Texto")],
                              readonly=True)
    linha_ids = fields.One2many("boteco.importar.orcamento.linha", "importacao_id", string="Itens encontrados")
    lido = fields.Boolean()
    registrados = fields.Integer(readonly=True)

    # ------------------------------------------------------------------
    @api.model
    def _insumos_candidatos(self):
        """Só insumos e bebidas de revenda: nunca prato, drink preparado ou item produzido (receita)."""
        Produto = self.env["product.product"].sudo()
        produtos = Produto.search([("purchase_ok", "=", True)], limit=5000)
        bebidas = ("bebida_giro", "garrafa", "agua")

        def serve(p):
            t = p.product_tmpl_id
            if getattr(t, "boteco_bebida_preparada", False) or t.bom_ids:
                return False
            if not t.available_in_pos:
                return True
            return (t.boteco_tipo_consumo in bebidas) or (t.boteco_setor_id.codigo == "bar" and not t.boteco_tipo_consumo)

        return produtos.filtered(serve)

    @api.model
    def _uom_do_insumo(self, produto):
        uom = produto.uom_po_id or produto.uom_id
        refs = {"weight": "uom.product_uom_categ_kgm", "volume": "uom.product_uom_categ_vol"}
        for categoria, xmlid in refs.items():
            if uom.category_id == self.env.ref(xmlid, raise_if_not_found=False):
                return categoria, 1.0 / (uom.factor or 1.0)
        return "unit", 1.0

    @api.model
    def _casar_insumo(self, descricao, fornecedor=None, unidade=None):
        """Descrição do fornecedor -> {produto, certeza ('alta'|'media'|''), fator, motivo}.

        * 'alta': de-para aprendido, código/nome do fornecedor, nome igual, ou todas as palavras do insumo
          presentes e o tamanho batendo (e a embalagem entendida). Pode gravar o preço sozinho.
        * 'media': parecido. Vai para "Cotações para revisar" com a sugestão já marcada (1 toque).
        """
        from ..tools import casamento

        Produto = self.env["product.product"]
        vazio = {"produto": Produto, "certeza": "", "fator": 1.0, "motivo": ""}
        if fornecedor:
            mapa = self.env["boteco.nfe.produto"].search(
                [("partner_id", "=", fornecedor.id), ("descricao", "=ilike", descricao)], limit=1)
            if mapa:
                return {"produto": mapa.product_id, "certeza": "alta", "fator": mapa.fator or 1.0, "motivo": "de-para"}
            info = self.env["product.supplierinfo"].search(
                [("partner_id", "=", fornecedor.id), ("product_name", "=ilike", descricao)], limit=1)
            if info:
                produto = info.product_id or info.product_tmpl_id.product_variant_id
                fator, _certo = casamento.quantidade_no_insumo(descricao, unidade, self._uom_do_insumo(produto))
                return {"produto": produto, "certeza": "alta", "fator": fator, "motivo": "nome do fornecedor"}
        candidatos = self._insumos_candidatos()
        alvo = casamento.sem_acento(descricao).strip()
        notas = []
        for produto in candidatos:
            if casamento.sem_acento(produto.name).strip() == alvo:
                notas = [(2.0, produto)]
                break
            nota = casamento.pontuar(descricao, produto.name)
            if nota >= 0.5:
                notas.append((nota + 0.01 * len(casamento.palavras(produto.name)), produto))
        if not notas:
            return vazio
        notas.sort(key=lambda n: -n[0])
        melhor_nota, produto = notas[0]
        empate = len(notas) > 1 and abs(notas[1][0] - melhor_nota) < 1e-9
        fator, certo = casamento.quantidade_no_insumo(descricao, unidade, self._uom_do_insumo(produto))
        # Insumo com tamanho no nome ("Cerveja 600 ml") e cotação sem tamanho ("Cerveja Brahma"): pode ser lata
        sem_tamanho = bool(casamento.medida(produto.name)) and not casamento.medida(descricao)
        alta = melhor_nota >= 1.0 and not empate and certo and (melhor_nota >= 2.0 or not sem_tamanho)
        return {"produto": produto, "certeza": "alta" if alta else "media", "fator": fator,
                "motivo": "nome igual" if melhor_nota >= 2.0 else ("todas as palavras" if melhor_nota >= 1.0 else "parecido")}

    @api.model
    def _achar_insumo(self, descricao, fornecedor=None):
        """Sugestão de insumo para a tela de leitura (quem lê confere antes de gravar)."""
        return self._casar_insumo(descricao, fornecedor)["produto"]

    def action_ler(self):
        self.ensure_one()
        if not self.env.company.boteco_recurso_ativo("leitor_orcamento_pdf_imagem"):
            raise UserError(_("O leitor de orçamentos está desligado na Central de Recursos."))
        if self.arquivo:
            conteudo = base64.b64decode(self.arquivo)
            if conteudo[:4] != b"%PDF" and not (self.nome_arquivo or "").lower().endswith(".pdf"):
                raise UserError(_("Aqui só PDF ou texto. Fotos de encarte entram pelo serviço de cotações "
                                  "(o fornecedor manda no WhatsApp do bar)."))
            itens = orcamento.ler_texto(orcamento.texto_do_pdf(conteudo))
            if not itens:
                raise UserError(_("Não achei preços no texto deste PDF. Se for PDF escaneado, mande pelo WhatsApp do bar."))
            origem = "orcamento_pdf"
        elif self.texto:
            itens = orcamento.ler_texto(self.texto)
            origem = "orcamento_texto"
        else:
            raise UserError(_("Envie um PDF ou cole o texto do orçamento."))
        linhas = [fields.Command.clear()]
        De = self.env["boteco.nfe.produto"]
        for item in itens:
            casou = self._casar_insumo(item["descricao"], self.partner_id, item["unidade"])
            linhas.append(fields.Command.create({
                "descricao": item["descricao"], "unidade": item["unidade"], "preco": item["preco"],
                "product_id": casou["produto"].id, "fator": casou["fator"] or 1.0,
            }))
        self.write({"linha_ids": linhas, "lido": True, "origem": origem})
        return self._reabrir()

    def _reabrir(self):
        return {"type": "ir.actions.act_window", "res_model": self._name, "res_id": self.id, "view_mode": "form",
                "target": "new"}

    def action_registrar(self):
        """Grava as cotações no histórico (radar de preços) e aprende o de-para do fornecedor."""
        self.ensure_one()
        if not self.lido:
            self.action_ler()
        Historico = self.env["boteco.historico.preco"]
        De = self.env["boteco.nfe.produto"]
        registrados = 0
        referencia = self.nome_arquivo or _("Orçamento %s", self.data)
        for linha in self.linha_ids.filtered("product_id"):
            preco = linha.preco / (linha.fator or 1.0)
            if Historico.registrar(linha.product_id, preco, fornecedor=self.partner_id, origem=self.origem or "manual",
                                   referencia=referencia, data=self.data, descricao=linha.descricao):
                registrados += 1
            codigo = "orc:" + re.sub(r"\s+", " ", linha.descricao.lower()).strip()[:60]
            if not De.search_count([("partner_id", "=", self.partner_id.id), ("codigo", "=", codigo)]):
                De.create({"partner_id": self.partner_id.id, "codigo": codigo, "descricao": linha.descricao,
                           "product_id": linha.product_id.id, "fator": linha.fator or 1.0})
        self.registrados = registrados
        return {
            "type": "ir.actions.act_window", "res_model": "boteco.historico.preco", "view_mode": "list,form",
            "name": _("Cotações registradas"),
            "domain": [("partner_id", "=", self.partner_id.id), ("data", "=", self.data)],
        }


class BotecoImportarOrcamentoLinha(models.TransientModel):
    _name = "boteco.importar.orcamento.linha"
    _description = "Item do orçamento lido"

    importacao_id = fields.Many2one("boteco.importar.orcamento", required=True, ondelete="cascade")
    descricao = fields.Char("Como veio escrito")
    unidade = fields.Char("Un.")
    preco = fields.Float("Preço", digits="Product Price")
    product_id = fields.Many2one("product.product", string="Insumo")
    fator = fields.Float("Fator", default=1.0, help="Unidades do estoque por unidade do orçamento (ex.: caixa com 20 kg = 20).")
