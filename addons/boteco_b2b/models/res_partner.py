from datetime import timedelta

from odoo import _, api, fields, models
from odoo.exceptions import UserError


class ResPartner(models.Model):
    _inherit = "res.partner"

    boteco_cliente_b2b = fields.Boolean("Bar cliente (B2B)")
    boteco_ie = fields.Char("Inscrição estadual", help="Para a NF-e emitida depois. 'ISENTO' se for o caso.")
    boteco_dias_alerta = fields.Integer("Avisar se ficar sem comprar (dias)", default=14)
    boteco_ultima_compra = fields.Date("Última compra", compute="_compute_boteco_compras", store=True)
    boteco_total_comprado = fields.Monetary("Total comprado", compute="_compute_boteco_compras", store=True,
                                            currency_field="currency_id")
    boteco_kg_comprados = fields.Float("Kg comprados", compute="_compute_boteco_compras", store=True)
    boteco_parado = fields.Boolean("Parou de comprar", compute="_compute_boteco_parado", search="_search_boteco_parado")
    boteco_contrato_ids = fields.One2many("boteco.contrato.assessoria", "partner_id", string="Contratos de assessoria")

    @api.depends("sale_order_ids.state", "sale_order_ids.date_order", "sale_order_ids.amount_total")
    def _compute_boteco_compras(self):
        for parceiro in self:
            pedidos = parceiro.sale_order_ids.filtered(lambda p: p.state == "sale")
            parceiro.boteco_ultima_compra = max(pedidos.mapped("date_order")).date() if pedidos else False
            parceiro.boteco_total_comprado = sum(pedidos.mapped("amount_total"))
            kg = self.env.ref("uom.product_uom_kgm")
            parceiro.boteco_kg_comprados = sum(
                l.product_uom._compute_quantity(l.product_uom_qty, kg)
                for l in pedidos.order_line if l.product_uom.category_id == kg.category_id
            )

    def _compute_boteco_parado(self):
        hoje = fields.Date.context_today(self)
        for parceiro in self:
            parceiro.boteco_parado = bool(
                parceiro.boteco_cliente_b2b and parceiro.boteco_ultima_compra
                and (hoje - parceiro.boteco_ultima_compra).days > (parceiro.boteco_dias_alerta or 14)
            )

    def _search_boteco_parado(self, operator, value):
        parados = self.search([("boteco_cliente_b2b", "=", True), ("boteco_ultima_compra", "!=", False)]).filtered("boteco_parado")
        if (operator == "=" and value) or (operator == "!=" and not value):
            return [("id", "in", parados.ids)]
        return [("id", "not in", parados.ids)]

    def action_boteco_repetir_ultimo_pedido(self):
        """Um toque: copia o último pedido do bar com entrega amanhã."""
        self.ensure_one()
        ultimo = self.env["sale.order"].search([("partner_id", "child_of", self.commercial_partner_id.id),
                                                ("state", "in", ("sale", "done"))], order="date_order desc", limit=1)
        if not ultimo:
            raise UserError(_("%s ainda não tem pedido para repetir.", self.name))
        novo = ultimo.copy({"commitment_date": fields.Datetime.now() + timedelta(days=1)})
        return {"type": "ir.actions.act_window", "res_model": "sale.order", "res_id": novo.id, "view_mode": "form"}

    @api.model
    def _cron_alertar_clientes_parados(self):
        """Cria uma atividade para o comercial ligar para o bar que parou de comprar."""
        tipo = self.env.ref("mail.mail_activity_data_call", raise_if_not_found=False)
        for parceiro in self.search([("boteco_parado", "=", True)]):
            ja_tem = self.env["mail.activity"].search_count([
                ("res_model", "=", "res.partner"), ("res_id", "=", parceiro.id), ("summary", "ilike", "parou de comprar")])
            if ja_tem:
                continue
            responsavel = parceiro.user_id or self.env.ref("base.user_admin")
            parceiro.activity_schedule(
                activity_type_id=tipo.id if tipo else False,
                summary=_("Cliente parou de comprar"),
                note=_("Última compra em %s. Ligue para saber se precisa de algo.",
                       parceiro.boteco_ultima_compra.strftime("%d/%m/%Y")),
                user_id=responsavel.id,
            )
        return True
