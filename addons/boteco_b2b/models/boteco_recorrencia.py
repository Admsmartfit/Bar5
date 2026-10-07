from datetime import timedelta

from odoo import _, api, fields, models

DIAS = [("0", "Segunda"), ("1", "Terça"), ("2", "Quarta"), ("3", "Quinta"), ("4", "Sexta"), ("5", "Sábado"), ("6", "Domingo")]


class BotecoB2bRecorrencia(models.Model):
    """Pedido que se repete toda semana (ex.: toda quinta, 20 kg de bolinho)."""

    _name = "boteco.b2b.recorrencia"
    _description = "Pedido recorrente B2B"
    _order = "partner_id"

    name = fields.Char(compute="_compute_name", store=True)
    partner_id = fields.Many2one("res.partner", string="Bar cliente", required=True, domain=[("boteco_cliente_b2b", "=", True)])
    dia_entrega = fields.Selection(DIAS, string="Entregar toda", required=True, default="3")
    antecedencia_dias = fields.Integer("Gerar o pedido com antecedência de (dias)", default=1)
    linha_ids = fields.One2many("boteco.b2b.recorrencia.linha", "recorrencia_id", string="Produtos")
    active = fields.Boolean(default=True)
    ultimo_pedido_id = fields.Many2one("sale.order", readonly=True)
    proxima_entrega = fields.Date(compute="_compute_proxima_entrega")
    company_id = fields.Many2one("res.company", default=lambda s: s.env.company)

    @api.depends("partner_id", "dia_entrega")
    def _compute_name(self):
        for r in self:
            r.name = "%s – toda %s" % (r.partner_id.name or "", dict(DIAS).get(r.dia_entrega, "").lower())

    def _compute_proxima_entrega(self):
        hoje = fields.Date.context_today(self)
        for r in self:
            dias = (int(r.dia_entrega) - hoje.weekday()) % 7 or 7
            r.proxima_entrega = hoje + timedelta(days=dias)

    def action_gerar_pedido(self, data_entrega=None):
        """Um toque: cria o pedido confirmado para a próxima entrega."""
        pedidos = self.env["sale.order"]
        for r in self:
            entrega = data_entrega or r.proxima_entrega
            pedido = self.env["sale.order"].create({
                "partner_id": r.partner_id.id,
                "commitment_date": fields.Datetime.to_datetime(entrega) + timedelta(hours=10),
                "boteco_recorrencia_id": r.id,
                "order_line": [fields.Command.create({"product_id": l.product_id.id, "product_uom_qty": l.quantidade})
                               for l in r.linha_ids],
            })
            pedido.action_confirm()
            r.ultimo_pedido_id = pedido
            pedidos |= pedido
        if len(pedidos) == 1:
            return {"type": "ir.actions.act_window", "res_model": "sale.order", "res_id": pedidos.id, "view_mode": "form"}
        return True

    @api.model
    def _cron_gerar_pedidos(self):
        hoje = fields.Date.context_today(self)
        for r in self.search([]):
            entrega = r.proxima_entrega
            if (entrega - hoje).days > (r.antecedencia_dias or 1):
                continue
            ja_existe = self.env["sale.order"].search_count([
                ("boteco_recorrencia_id", "=", r.id), ("state", "!=", "cancel"),
                ("commitment_date", ">=", fields.Datetime.to_datetime(entrega)),
                ("commitment_date", "<", fields.Datetime.to_datetime(entrega + timedelta(days=1))),
            ])
            if not ja_existe:
                r.action_gerar_pedido(entrega)
        return True


class BotecoB2bRecorrenciaLinha(models.Model):
    _name = "boteco.b2b.recorrencia.linha"
    _description = "Produto do pedido recorrente"

    recorrencia_id = fields.Many2one("boteco.b2b.recorrencia", required=True, ondelete="cascade")
    product_id = fields.Many2one("product.product", string="Produto", required=True, domain=[("sale_ok", "=", True)])
    quantidade = fields.Float("Quantidade", required=True, default=1.0)
    unidade = fields.Char(related="product_id.uom_id.name")
