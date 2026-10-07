from odoo import fields, models


class StockWarehouse(models.Model):
    _inherit = "stock.warehouse"

    boteco_tipo_unidade = fields.Selection(
        [("bar", "Bar"), ("cozinha_central", "Cozinha central")],
        string="Tipo de unidade",
        help="Usado para separar o estoque do bar e o da cozinha central nos relatórios.",
    )
