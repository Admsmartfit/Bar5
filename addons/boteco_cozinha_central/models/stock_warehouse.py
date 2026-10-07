from odoo import fields, models


class StockWarehouse(models.Model):
    _inherit = "stock.warehouse"

    boteco_impressora_etiqueta_id = fields.Many2one(
        "boteco.impressora", string="Impressora de etiquetas",
        domain="[('linguagem', 'in', ('zpl', 'tspl'))]",
        help="Etiqueta do saco a vácuo sai aqui quando a produção é finalizada.",
    )
