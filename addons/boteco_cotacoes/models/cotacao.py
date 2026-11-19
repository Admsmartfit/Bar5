"""Cotações automáticas (Etapa 35): WhatsApp do bar (QR Code) e coletor externo de sites/Instagram."""

import base64
import logging
import re
import secrets
from datetime import timedelta

from odoo import _, api, fields, models
from odoo.exceptions import UserError

from odoo.addons.boteco_estoque.tools import orcamento

_logger = logging.getLogger(__name__)

PARAM_TOKEN_WHATSAPP = "boteco.cotacoes_token_whatsapp"
PARAM_TOKEN_COLETOR = "boteco.cotacoes_token_coletor"
DIAS_GUARDAR = 30  # LGPD: o conteúdo original da mensagem/arquivo fica 30 dias e é apagado


def so_digitos(numero):
    """Telefone -> só dígitos com DDI 55 (como o WhatsApp manda)."""
    digitos = re.sub(r"\D", "", numero or "")
    if digitos and not digitos.startswith("55") and len(digitos) in (10, 11):
        digitos = "55" + digitos
    return digitos


def mesmo_numero(a, b):
    """Celular com e sem o 9º dígito (o WhatsApp às vezes manda sem)."""
    a, b = so_digitos(a), so_digitos(b)
    if not a or not b:
        return False
    if a == b:
        return True
    sem9 = lambda n: n[:4] + n[5:] if len(n) == 13 and n[4] == "9" else n  # noqa: E731
    return sem9(a) == sem9(b)


class ResCompany(models.Model):
    _inherit = "res.company"

    boteco_flag_cotacoes_whatsapp = fields.Boolean("Receber cotações dos fornecedores pelo WhatsApp", default=True)
    boteco_flag_coletor_ofertas = fields.Boolean("Coletor externo de ofertas (sites e Instagram)", default=True)


class ResPartner(models.Model):
    _inherit = "res.partner"

    boteco_cotacao_confiavel = fields.Boolean(
        "Aceitar cotações automáticas", default=True,
        help="Mensagens de preço deste fornecedor pelo WhatsApp e ofertas do site/Instagram entram sozinhas no radar.")
    boteco_site_ofertas = fields.Char("Site / encarte de ofertas", help="Endereço da página de ofertas do fornecedor.")
    boteco_palavras_chave = fields.Char(
        "Palavras-chave das ofertas", help="Separadas por vírgula. Ex.: cerveja 600ml, oferta, R$. Em branco: tudo com preço.")

    @api.model
    def _boteco_fornecedor_do_numero(self, numero):
        """Fornecedor confiável com esse celular (só fornecedores: nunca cliente, família ou grupo)."""
        digitos = so_digitos(numero)
        if len(digitos) < 10:
            return self.browse()
        fim = digitos[-8:]
        candidatos = self.sudo().search([
            ("boteco_cotacao_confiavel", "=", True), ("supplier_rank", ">", 0),
            "|", ("mobile", "ilike", fim[:4]), ("phone", "ilike", fim[:4]),
        ])
        for parceiro in candidatos:
            if mesmo_numero(parceiro.mobile, digitos) or mesmo_numero(parceiro.phone, digitos):
                return parceiro
        return self.browse()


class BotecoHistoricoPreco(models.Model):
    _inherit = "boteco.historico.preco"

    origem = fields.Selection(selection_add=[("whatsapp", "WhatsApp do fornecedor"), ("site", "Site do fornecedor")],
                              ondelete={"whatsapp": "set default", "site": "set default"})


class BotecoCotacaoLog(models.Model):
    """Registro de cada chamada (quem, quando, quantos itens). Nunca guarda conversa de quem não é fornecedor."""

    _name = "boteco.cotacao.log"
    _description = "Registro das integrações de cotação"
    _order = "create_date desc, id desc"

    canal = fields.Selection([("whatsapp", "WhatsApp"), ("coletor", "Coletor"), ("conexao", "Conexão do WhatsApp")],
                             required=True)
    resultado = fields.Selection([
        ("ok", "Recebido"), ("recusado", "Recusado (token)"), ("desconhecido", "Número não cadastrado"),
        ("ignorado", "Ignorado"), ("erro", "Erro"), ("limite", "Acima do limite por minuto"),
    ], required=True)
    partner_id = fields.Many2one("res.partner", string="Fornecedor")
    itens = fields.Integer()
    ip = fields.Char("Endereço")
    detalhe = fields.Char()

    @api.model
    def registrar(self, canal, resultado, **vals):
        return self.sudo().create({"canal": canal, "resultado": resultado, **vals})

    @api.model
    def _boteco_acima_do_limite(self, canal, por_minuto=60):
        desde = fields.Datetime.now() - timedelta(minutes=1)
        return self.sudo().search_count([("canal", "=", canal), ("create_date", ">=", desde)]) >= por_minuto


class BotecoCotacaoFila(models.Model):
    """Mensagens de fornecedor esperando leitura (o webhook responde na hora; o cron lê em seguida)."""

    _name = "boteco.cotacao.fila"
    _description = "Fila de cotações a ler"
    _order = "id"

    partner_id = fields.Many2one("res.partner", string="Fornecedor", required=True)
    canal = fields.Selection([("whatsapp", "WhatsApp"), ("coletor", "Coletor")], required=True, default="whatsapp")
    tipo = fields.Selection([("texto", "Texto"), ("pdf", "PDF"), ("imagem", "Foto")], required=True, default="texto")
    texto = fields.Text()
    arquivo = fields.Binary(attachment=True)
    mimetype = fields.Char()
    referencia = fields.Char()
    estado = fields.Selection([("pendente", "Pendente"), ("lido", "Lido"), ("erro", "Erro")], default="pendente",
                              required=True, index=True)
    itens = fields.Integer()
    erro = fields.Char()
    company_id = fields.Many2one("res.company", required=True, default=lambda s: s.env.company)

    def _ler(self):
        """Texto / PDF / foto -> itens com o mesmo parser da Etapa 18."""
        self.ensure_one()
        if self.tipo == "texto":
            return orcamento.ler_texto(self.texto)
        conteudo = base64.b64decode(self.arquivo or b"")
        if self.tipo == "pdf":
            return orcamento.ler_texto(orcamento.texto_do_pdf(conteudo))
        return self.env["boteco.importar.orcamento"]._ler_imagem(conteudo, self.mimetype or "image/jpeg")

    @api.model
    def _cron_processar(self):
        Cotacao = self.env["boteco.cotacao.revisar"]
        for item in self.sudo().search([("estado", "=", "pendente")], limit=200):
            try:
                with self.env.cr.savepoint():
                    origem = "whatsapp" if item.canal == "whatsapp" else "site"
                    itens = item._ler()
                    for dado in itens:
                        Cotacao._aplicar(item.partner_id, dado, origem, item.referencia)
                    item.write({"estado": "lido", "itens": len(itens), "texto": False, "arquivo": False})
            except Exception as erro:  # noqa: BLE001 — um fornecedor com problema não para os outros
                _logger.warning("Cotação %s não foi lida", item.id, exc_info=True)
                item.write({"estado": "erro", "erro": str(erro)[:200]})
        # LGPD: o que veio do fornecedor some depois de 30 dias
        self.sudo().search([("create_date", "<", fields.Datetime.now() - timedelta(days=DIAS_GUARDAR))]).unlink()
        self.env["boteco.cotacao.log"].sudo().search(
            [("create_date", "<", fields.Datetime.now() - timedelta(days=90))]).unlink()
        return True

    @api.model
    def _boteco_enfileirar(self, vals):
        fila = self.sudo().create(vals)
        cron = self.env.ref("boteco_cotacoes.cron_processar_cotacoes", raise_if_not_found=False)
        if cron:
            cron.sudo()._trigger()  # lê já, em segundo plano (não segura a resposta do webhook)
        return fila


class BotecoCotacaoRevisar(models.Model):
    """Itens que vieram do fornecedor e não casaram com nenhum insumo: 1 toque para ligar."""

    _name = "boteco.cotacao.revisar"
    _description = "Cotação para revisar"
    _order = "create_date desc, id desc"

    partner_id = fields.Many2one("res.partner", string="Fornecedor", required=True)
    descricao = fields.Char("Como veio escrito", required=True)
    preco = fields.Float(digits="Product Price")
    unidade = fields.Char()
    origem = fields.Char()
    referencia = fields.Char()
    product_id = fields.Many2one("product.product", string="É o insumo", domain=[("purchase_ok", "=", True)])
    fator = fields.Float("Unidades do insumo por unidade do fornecedor", default=1.0)
    estado = fields.Selection([("revisar", "Revisar"), ("ligado", "Ligado"), ("descartado", "Descartado")],
                              default="revisar", required=True, index=True)

    @api.model
    def _aplicar(self, fornecedor, item, origem, referencia=None):
        """Casa com o insumo (de-para que aprende sozinho) e grava radar + preço do fornecedor; senão, vai revisar."""
        produto = self.env["boteco.importar.orcamento"]._achar_insumo(item["descricao"], fornecedor)
        if not produto:
            existe = self.sudo().search_count([("partner_id", "=", fornecedor.id), ("estado", "=", "revisar"),
                                               ("descricao", "=ilike", item["descricao"])])
            if not existe:
                self.sudo().create({"partner_id": fornecedor.id, "descricao": item["descricao"][:120],
                                    "preco": item["preco"], "unidade": item.get("unidade") or False,
                                    "origem": origem, "referencia": referencia})
            return self.env["boteco.historico.preco"]
        mapa = self.env["boteco.nfe.produto"].sudo().search(
            [("partner_id", "=", fornecedor.id), ("descricao", "=ilike", item["descricao"])], limit=1)
        preco = item["preco"] / (mapa.fator or 1.0) if mapa else item["preco"]
        return self._gravar(fornecedor, produto, preco, origem, referencia, item["descricao"])

    @api.model
    def _gravar(self, fornecedor, produto, preco, origem, referencia, descricao):
        registro = self.env["boteco.historico.preco"].registrar(
            produto, preco, fornecedor=fornecedor, origem=origem, referencia=referencia, descricao=descricao)
        # Preço do fornecedor no produto (o que o Odoo usa nas compras)
        Info = self.env["product.supplierinfo"].sudo()
        info = Info.search([("partner_id", "=", fornecedor.id), ("product_tmpl_id", "=", produto.product_tmpl_id.id)],
                           limit=1)
        if info:
            info.price = preco
        else:
            Info.create({"partner_id": fornecedor.id, "product_tmpl_id": produto.product_tmpl_id.id,
                         "product_id": produto.id, "price": preco, "product_name": descricao[:120]})
        return registro

    def action_ligar(self):
        De = self.env["boteco.nfe.produto"].sudo()
        for item in self:
            if not item.product_id:
                raise UserError(_("Escolha o insumo de \"%s\".", item.descricao))
            codigo = "orc:" + re.sub(r"\s+", " ", item.descricao.lower()).strip()[:60]
            if not De.search_count([("partner_id", "=", item.partner_id.id), ("codigo", "=", codigo)]):
                De.create({"partner_id": item.partner_id.id, "codigo": codigo, "descricao": item.descricao,
                           "product_id": item.product_id.id, "fator": item.fator or 1.0})
            self._gravar(item.partner_id, item.product_id, item.preco / (item.fator or 1.0),
                         item.origem if item.origem in ("whatsapp", "site", "instagram") else "manual",
                         item.referencia, item.descricao)
            item.estado = "ligado"
        return True

    def action_descartar(self):
        self.write({"estado": "descartado"})


class BotecoCotacoes(models.AbstractModel):
    """Tokens das integrações e as fontes para o coletor."""

    _name = "boteco.cotacoes"
    _description = "Integrações de cotação"

    @api.model
    def _token(self, parametro):
        Param = self.env["ir.config_parameter"].sudo()
        token = Param.get_param(parametro)
        if not token:
            token = secrets.token_urlsafe(24)
            Param.set_param(parametro, token)
        return token

    @api.model
    def trocar_token(self, qual):
        parametro = PARAM_TOKEN_WHATSAPP if qual == "whatsapp" else PARAM_TOKEN_COLETOR
        self.env["ir.config_parameter"].sudo().set_param(parametro, secrets.token_urlsafe(24))
        return self._token(parametro)

    @api.model
    def fontes(self):
        """O que o coletor deve ler e quando (horários configurados no Odoo)."""
        Param = self.env["ir.config_parameter"].sudo()
        fornecedores = self.env["res.partner"].sudo().search([
            ("boteco_cotacao_confiavel", "=", True), ("supplier_rank", ">", 0),
            "|", ("boteco_site_ofertas", "!=", False), ("boteco_instagram_handle", "!=", False)])
        return {
            "instagram_hora": Param.get_param("boteco.instagram_hora", "08:00"),
            "sites_dias": Param.get_param("boteco.coletor_sites_dias", "0,3"),  # 0 = segunda, 3 = quinta
            "sites_hora": Param.get_param("boteco.coletor_sites_hora", "08:00"),
            "fontes": [{
                "fornecedor_id": f.id, "nome": f.name, "site": f.boteco_site_ofertas or "",
                "instagram": f.boteco_instagram_handle or "",
                "palavras": [p.strip() for p in (f.boteco_palavras_chave or "").split(",") if p.strip()],
            } for f in fornecedores],
        }

    @api.model
    def receber_do_coletor(self, dados):
        """Itens extraídos pelo coletor (ou o texto da página/post, que o Odoo lê com o mesmo parser)."""
        Fila = self.env["boteco.cotacao.fila"]
        Cotacao = self.env["boteco.cotacao.revisar"]
        total = 0
        for bloco in dados.get("cotacoes") or []:
            fornecedor = self.env["res.partner"].sudo().browse(int(bloco.get("fornecedor_id") or 0)).exists()
            if not fornecedor or not fornecedor.boteco_cotacao_confiavel:
                continue
            origem = "instagram" if bloco.get("fonte") == "instagram" else "site"
            referencia = (bloco.get("link") or "")[:250] or False
            for item in bloco.get("itens") or []:
                try:
                    preco = float(str(item.get("preco")).replace(",", "."))
                except (TypeError, ValueError):
                    continue
                if item.get("produto") and preco > 0:
                    Cotacao._aplicar(fornecedor, {"descricao": str(item["produto"])[:120], "preco": preco,
                                                  "unidade": item.get("unidade") or ""}, origem, referencia)
                    total += 1
            if bloco.get("texto"):
                Fila._boteco_enfileirar({"partner_id": fornecedor.id, "canal": "coletor", "tipo": "texto",
                                         "texto": str(bloco["texto"])[:20000], "referencia": referencia})
                total += 1
        if "coletor_versao" in dados:
            self.env["ir.config_parameter"].sudo().set_param("boteco.coletor_visto_em", fields.Datetime.to_string(fields.Datetime.now()))
        return total


class ResPartnerInstagram(models.Model):
    _inherit = "res.partner"

    @api.model
    def _cron_monitorar_instagram(self):
        """Com o coletor externo ligado e funcionando, o Instagram sai do servidor do PDV (regra do PRD)."""
        company = self.env.company
        visto = self.env["ir.config_parameter"].sudo().get_param("boteco.coletor_visto_em")
        coletor_vivo = visto and fields.Datetime.to_datetime(visto) > fields.Datetime.now() - timedelta(days=2)
        if company.boteco_recurso_ativo("coletor_ofertas") and coletor_vivo:
            return True
        return super()._cron_monitorar_instagram()


class BotecoListaComprasLinha(models.TransientModel):
    _inherit = "boteco.lista.compras.linha"

    melhor_preco = fields.Text("Melhor preço encontrado (onde)")


class BotecoListaCompras(models.TransientModel):
    _inherit = "boteco.lista.compras"

    def action_gerar(self):
        resultado = super().action_gerar()
        Historico = self.env["boteco.historico.preco"].sudo()
        rotulos = dict(Historico._fields["origem"]._description_selection(self.env))
        for linha in self.linha_ids:
            partes = []
            for nome in re.findall(r"^• (.+?): ", linha.itens or "", re.M):
                produto = self.env["product.product"].search([("name", "=", nome)], limit=1)
                melhor = Historico.search([("product_id", "=", produto.id), ("company_id", "=", self.env.company.id),
                                           ("data", ">=", fields.Date.context_today(self) - timedelta(days=30))],
                                          order="preco_unitario asc, data desc", limit=1) if produto else Historico
                if melhor:
                    partes.append("%s: R$ %.2f – %s (%s, %s)" % (
                        nome, melhor.preco_unitario, melhor.partner_id.name or "?", rotulos.get(melhor.origem, ""),
                        melhor.data.strftime("%d/%m")))
            linha.melhor_preco = "\n".join(partes) or False
        return resultado
