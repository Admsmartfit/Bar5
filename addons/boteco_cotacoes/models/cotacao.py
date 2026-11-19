"""Cotações recebidas do serviço externo (n8n + Evolution API + IA) pela API — 19/11/2026.

O Odoo não conversa mais com WhatsApp, sites, Instagram nem fotos: o serviço externo faz isso e manda
só dados limpos (fornecedor, produto, unidade, preço). Aqui o Odoo é o cérebro financeiro e de estoque:
grava a cotação, atualiza o pedido de cotação em aberto e o preço do fornecedor, e alimenta o radar.
"""

import logging
import secrets
from datetime import timedelta

from odoo import _, api, fields, models

_logger = logging.getLogger(__name__)

PARAM_TOKEN = "boteco.cotacoes_token_api"
ROTA = "/api/boteco/webhook/cotacao_recebida"
# Unidades que o serviço externo pode mandar -> unidade do Odoo (xmlid)
UNIDADES = {
    "un": "uom.product_uom_unit", "und": "uom.product_uom_unit", "unidade": "uom.product_uom_unit",
    "kg": "uom.product_uom_kgm", "g": "uom.product_uom_gram", "l": "uom.product_uom_litre", "lt": "uom.product_uom_litre",
    "dz": "uom.product_uom_dozen", "duzia": "uom.product_uom_dozen",
}
EMBALAGENS = {"cx", "caixa", "fardo", "pct", "pacote", "saco", "sc", "bandeja", "pack"}


class ResCompany(models.Model):
    _inherit = "res.company"

    boteco_flag_cotacoes_externas = fields.Boolean(
        "Receber cotações do serviço externo (API)", default=True,
        help="O serviço de cotações (WhatsApp, sites, Instagram, fotos) manda os preços já limpos para o Odoo.")


class ResPartner(models.Model):
    _inherit = "res.partner"

    boteco_id_externo = fields.Char(
        "ID no serviço de cotações", index=True, copy=False,
        help="Como o serviço externo (n8n) identifica este fornecedor. O ID do Odoo também é aceito.")
    boteco_cotacao_confiavel = fields.Boolean(
        "Aceitar cotações automáticas", default=True,
        help="Preços deste fornecedor que chegam pela API entram sozinhos no radar.")

    _sql_constraints = [("boteco_id_externo_unico", "unique(boteco_id_externo)",
                         "Esse ID do serviço de cotações já está em outro fornecedor.")]


class BotecoHistoricoPreco(models.Model):
    _inherit = "boteco.historico.preco"

    # whatsapp/site ficam só para o histórico antigo; o que chega agora é "servico_externo"
    origem = fields.Selection(
        selection_add=[("whatsapp", "WhatsApp do fornecedor"), ("site", "Site do fornecedor"),
                       ("servico_externo", "Serviço de cotações (API)")],
        ondelete={"whatsapp": "set default", "site": "set default", "servico_externo": "set default"})


class BotecoCotacaoLog(models.Model):
    """Registro de cada chamada da API (quem, quando, quantos itens, o que deu)."""

    _name = "boteco.cotacao.log"
    _description = "Registro da API de cotações"
    _order = "create_date desc, id desc"

    canal = fields.Selection([("api", "API de cotações")], required=True, default="api")
    resultado = fields.Selection([
        ("ok", "Recebido"), ("parcial", "Recebido com pendências"), ("recusado", "Recusado (token)"),
        ("erro", "Erro"), ("limite", "Acima do limite por minuto"),
    ], required=True)
    partner_id = fields.Many2one("res.partner", string="Fornecedor")
    itens = fields.Integer()
    ip = fields.Char("Endereço")
    detalhe = fields.Char()

    @api.model
    def registrar(self, resultado, **vals):
        return self.sudo().create({"canal": "api", "resultado": resultado, **vals})

    @api.model
    def _boteco_acima_do_limite(self, por_minuto=120):
        desde = fields.Datetime.now() - timedelta(minutes=1)
        return self.sudo().search_count([("create_date", ">=", desde)]) >= por_minuto

    @api.model
    def _cron_limpar(self):
        self.sudo().search([("create_date", "<", fields.Datetime.now() - timedelta(days=90))]).unlink()
        return True


class BotecoCotacaoRevisar(models.Model):
    """Itens que chegaram sem dar para identificar o insumo (ou com unidade que não converte): 1 toque para ligar."""

    _name = "boteco.cotacao.revisar"
    _description = "Cotação para revisar"
    _order = "create_date desc, id desc"

    partner_id = fields.Many2one("res.partner", string="Fornecedor", required=True)
    descricao = fields.Char("Como veio", required=True)
    preco = fields.Float(digits="Product Price")
    unidade = fields.Char()
    origem = fields.Char()
    referencia = fields.Char()
    motivo = fields.Char("Por que não entrou sozinho")
    product_id = fields.Many2one("product.product", string="É o insumo", domain=[("purchase_ok", "=", True)])
    fator = fields.Float("Unidades do insumo por unidade cotada", default=1.0)
    estado = fields.Selection([("revisar", "Revisar"), ("ligado", "Ligado"), ("descartado", "Descartado")],
                              default="revisar", required=True, index=True)

    def action_ligar(self):
        Cotacoes = self.env["boteco.cotacoes"]
        for item in self:
            if not item.product_id:
                from odoo.exceptions import UserError
                raise UserError(_("Escolha o insumo de \"%s\".", item.descricao))
            Cotacoes._aplicar_preco(item.partner_id, item.product_id, item.preco / (item.fator or 1.0),
                                    item.referencia, item.descricao)
            item.estado = "ligado"
        return True

    def action_descartar(self):
        self.write({"estado": "descartado"})


class BotecoCotacoes(models.AbstractModel):
    """Recebe as cotações limpas do serviço externo e aplica no Odoo."""

    _name = "boteco.cotacoes"
    _description = "Cotações recebidas pela API"

    # ------------------------------------------------------------------ token
    @api.model
    def _token(self):
        Param = self.env["ir.config_parameter"].sudo()
        token = Param.get_param(PARAM_TOKEN)
        if not token:
            token = secrets.token_urlsafe(32)
            Param.set_param(PARAM_TOKEN, token)
        return token

    @api.model
    def trocar_token(self):
        self.env["ir.config_parameter"].sudo().set_param(PARAM_TOKEN, secrets.token_urlsafe(32))
        return self._token()

    # ------------------------------------------------------------------ identificação
    @api.model
    def _fornecedor(self, ident):
        Parceiro = self.env["res.partner"].sudo()
        ident = str(ident or "").strip()
        if not ident:
            return Parceiro
        achado = Parceiro.search([("boteco_id_externo", "=", ident)], limit=1)
        if not achado and ident.isdigit():
            achado = Parceiro.browse(int(ident)).exists()
        return achado if achado and achado.boteco_cotacao_confiavel else Parceiro

    @api.model
    def _produto(self, item):
        Produto = self.env["product.product"].sudo()
        codigo_barras = str(item.get("codigo_barras") or "").strip()
        if codigo_barras:
            achado = Produto.search([("barcode", "=", codigo_barras)], limit=1)
            if achado:
                return achado
        ident = str(item.get("id_produto_interno") or "").strip()
        if not ident:
            return Produto
        achado = Produto.search([("default_code", "=", ident)], limit=1)
        if not achado and ident.isdigit():
            achado = Produto.browse(int(ident)).exists()
        return achado

    @api.model
    def _preco_no_insumo(self, produto, unidade, preco, embalagem=None):
        """Preço cotado (na unidade do serviço) -> preço por unidade do insumo. None se não dá para converter."""
        un = (unidade or "").strip().lower()
        uom_insumo = produto.uom_po_id or produto.uom_id
        if un in EMBALAGENS:
            n = float(embalagem or 0)
            return preco / n if n > 0 else None  # "cx" sem dizer quantas unidades: não dá para saber
        if un == "ml":
            uom = self.env.ref("uom.product_uom_litre")
            preco = preco * 1000.0  # preço por ml -> por litro
        elif un in UNIDADES:
            uom = self.env.ref(UNIDADES[un])
        elif not un:
            uom = uom_insumo
        else:
            uom = self.env["uom.uom"].sudo().search([("name", "=ilike", un)], limit=1)
            if not uom:
                return None
        if uom.category_id != uom_insumo.category_id:
            return None
        return uom._compute_price(preco, uom_insumo)

    # ------------------------------------------------------------------ aplicar
    @api.model
    def receber(self, dados):
        """Payload da API -> resultado por item. Aceita um item ou {"cotacoes": [...]}.

        Item: {id_fornecedor, id_produto_interno | codigo_barras, unidade_medida, preco_cotado,
               quantidade_embalagem?, descricao?, referencia?}
        """
        itens = dados.get("cotacoes") if isinstance(dados.get("cotacoes"), list) else [dados]
        resultados = []
        for i, item in enumerate(itens[:500]):
            try:
                with self.env.cr.savepoint():
                    resultados.append({"indice": i, **self._receber_item(item)})
            except Exception as erro:  # noqa: BLE001 — um item com problema não derruba os outros
                _logger.warning("Cotação %s não entrou", i, exc_info=True)
                resultados.append({"indice": i, "status": "erro", "motivo": str(erro)[:200]})
        return resultados

    @api.model
    def _receber_item(self, item):
        fornecedor = self._fornecedor(item.get("id_fornecedor"))
        if not fornecedor:
            return {"status": "recusado", "motivo": "fornecedor desconhecido ou sem 'aceitar cotações automáticas'"}
        try:
            preco = float(str(item.get("preco_cotado")).replace(",", "."))
        except (TypeError, ValueError):
            return {"status": "recusado", "motivo": "preco_cotado inválido"}
        if preco <= 0:
            return {"status": "recusado", "motivo": "preco_cotado precisa ser maior que zero"}
        unidade = item.get("unidade_medida") or ""
        descricao = (item.get("descricao") or "").strip()
        referencia = (item.get("referencia") or "").strip()[:250] or False
        produto = self._produto(item)
        preco_insumo = self._preco_no_insumo(produto, unidade, preco, item.get("quantidade_embalagem")) if produto else None
        if not produto or preco_insumo is None:
            motivo = (_("produto não encontrado") if not produto
                      else _("unidade '%(u)s' não converte para %(i)s", u=unidade, i=(produto.uom_po_id or produto.uom_id).name))
            self.env["boteco.cotacao.revisar"].sudo().create({
                "partner_id": fornecedor.id, "descricao": descricao or str(item.get("id_produto_interno") or "?")[:120],
                "preco": preco, "unidade": unidade or False, "origem": "servico_externo", "referencia": referencia,
                "product_id": produto.id or False, "motivo": motivo})
            return {"status": "revisar", "motivo": motivo}
        resultado = self._aplicar_preco(fornecedor, produto, preco_insumo, referencia, descricao)
        return {"status": "ok", "produto_id": produto.id, "preco_unidade_insumo": round(preco_insumo, 4), **resultado}

    @api.model
    def _aplicar_preco(self, fornecedor, produto, preco, referencia=None, descricao=None):
        """Histórico (radar), preço do fornecedor, cotação em aberto e regra de oportunidade."""
        self.env["boteco.historico.preco"].registrar(
            produto, preco, fornecedor=fornecedor, origem="servico_externo", referencia=referencia, descricao=descricao)
        Info = self.env["product.supplierinfo"].sudo()
        info = Info.search([("partner_id", "=", fornecedor.id), ("product_tmpl_id", "=", produto.product_tmpl_id.id)],
                           limit=1)
        if info:
            info.price = preco
        else:
            Info.create({"partner_id": fornecedor.id, "product_tmpl_id": produto.product_tmpl_id.id,
                         "product_id": produto.id, "price": preco})
        # Pedido de cotação (RFQ) em aberto deste fornecedor com o insumo: o preço da linha é atualizado em silêncio
        linhas = self.env["purchase.order.line"].sudo().search([
            ("order_id.partner_id", "=", fornecedor.commercial_partner_id.id), ("order_id.state", "in", ("draft", "sent")),
            ("product_id", "=", produto.id)])
        for linha in linhas:
            linha.price_unit = (produto.uom_po_id or produto.uom_id)._compute_price(preco, linha.product_uom)
        oportunidade = self.env["boteco.oportunidade.compra"]._avaliar(produto, fornecedor, preco)
        return {"rfq_atualizadas": len(linhas), "oportunidade_id": oportunidade.id or False}
