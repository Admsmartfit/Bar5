from odoo import fields, models


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
