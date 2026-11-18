from odoo import _, api, fields, models
from odoo.exceptions import UserError


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

    # ------------------------------------------------------------------
    # Etapa 17: venda B2B não consome a reserva mínima do bar
    # ------------------------------------------------------------------
    def _boteco_conferir_reserva_bar(self):
        for pedido in self:
            if not pedido.company_id.boteco_recurso_ativo("reserva_estoque_bar_b2b"):
                continue
            por_produto = {}
            for linha in pedido.order_line.filtered(lambda l: l.product_id.boteco_estoque_min_bar > 0):
                qtd = linha.product_uom._compute_quantity(linha.product_uom_qty, linha.product_id.uom_id)
                por_produto[linha.product_id] = por_produto.get(linha.product_id, 0.0) + qtd
            for produto, qtd in por_produto.items():
                outras = self.env["sale.order.line"].sudo().search([
                    ("product_id", "=", produto.id), ("order_id.state", "=", "sale"), ("order_id", "!=", pedido.id)])
                comprometido = sum(max(l.product_uom_qty - l.qty_delivered, 0.0) for l in outras)
                livre = produto.qty_available - comprometido - produto.boteco_estoque_min_bar
                if qtd > livre:
                    raise UserError(_(
                        "%(item)s: dá para vender no máximo %(livre).2f %(un)s para revenda. "
                        "Estoque %(est).2f, já vendido %(comp).2f e reserva do bar %(res).2f.",
                        item=produto.display_name, livre=max(livre, 0.0), un=produto.uom_id.name,
                        est=produto.qty_available, comp=comprometido, res=produto.boteco_estoque_min_bar,
                    ))

    def action_confirm(self):
        self._boteco_conferir_reserva_bar()
        return super().action_confirm()

    def _prepare_invoice(self):
        vals = super()._prepare_invoice()
        vals["boteco_frente"] = "b2b"
        return vals
