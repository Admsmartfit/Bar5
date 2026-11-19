from odoo import _, fields, models
from odoo.exceptions import UserError


class PosConfig(models.Model):
    _inherit = "pos.config"

    boteco_taxa_servico_pct = fields.Float("Taxa de serviço (%)", default=10.0,
                                           help="Sugerida em toda conta de mesa. Zero = sem taxa.")
    boteco_produto_taxa_id = fields.Many2one(
        "product.product", string="Produto da taxa de serviço",
        default=lambda s: s.env.ref("boteco_pos.produto_taxa_servico", raise_if_not_found=False),
    )
    boteco_produto_couvert_id = fields.Many2one(
        "product.product", string="Produto do couvert",
        default=lambda s: s.env.ref("boteco_pos.produto_couvert", raise_if_not_found=False),
    )
    boteco_taxa_no_balcao = fields.Boolean("Taxa também no balcão", help="Comanda avulsa sem mesa também leva taxa.")
    boteco_minutos_atraso = fields.Integer("Mesa atrasada após (min)", default=30,
                                           help="A mesa fica vermelha no mapa quando o último pedido passa deste tempo.")
    boteco_contagem_cega = fields.Boolean("Fechamento com contagem cega", default=True,
                                          help="O operador digita o que contou antes de ver o valor esperado.")

    def _get_special_products(self):
        """Taxa de serviço e couvert são lançados sozinhos: não aparecem na grade de produtos."""
        especiais = super()._get_special_products()
        for xmlid in ("boteco_pos.produto_taxa_servico", "boteco_pos.produto_couvert"):
            produto = self.env.ref(xmlid, raise_if_not_found=False)
            if produto:
                especiais |= produto
        configs = self.sudo().search([])
        return especiais | configs.boteco_produto_taxa_id | configs.boteco_produto_couvert_id

    def _check_before_creating_new_session(self):
        """Onboarding: o caixa só abre com pelo menos 1 item à venda e 1 forma de pagamento."""
        for config in self:
            extras = (config.boteco_produto_taxa_id | config.boteco_produto_couvert_id).ids
            itens = self.env["product.product"].sudo().search_count(
                [("available_in_pos", "=", True), ("sale_ok", "=", True), ("id", "not in", extras)], limit=1)
            if not itens:
                raise UserError(_("Antes de abrir o caixa, cadastre pelo menos um item do cardápio "
                                  "(Primeiros passos › Cardápio)."))
            if not config.payment_method_ids:
                raise UserError(_("Antes de abrir o caixa, escolha pelo menos uma forma de pagamento "
                                  "(Primeiros passos › Formas de pagamento)."))
        return super()._check_before_creating_new_session()
