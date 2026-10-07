from odoo import api, fields, models


class SaleOrder(models.Model):
    _inherit = "sale.order"

    boteco_recorrencia_id = fields.Many2one("boteco.b2b.recorrencia", string="Pedido recorrente", readonly=True,
                                            copy=False)
    boteco_kg_total = fields.Float("Total em kg", compute="_compute_boteco_kg_total")

    @api.depends("order_line.product_uom_qty", "order_line.product_uom")
    def _compute_boteco_kg_total(self):
        kg = self.env.ref("uom.product_uom_kgm")
        for pedido in self:
            pedido.boteco_kg_total = sum(
                l.product_uom._compute_quantity(l.product_uom_qty, kg)
                for l in pedido.order_line if l.product_uom.category_id == kg.category_id
            )

    def _prepare_invoice(self):
        vals = super()._prepare_invoice()
        vals["boteco_frente"] = "b2b"
        return vals
