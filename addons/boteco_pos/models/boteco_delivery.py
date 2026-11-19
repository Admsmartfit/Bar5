"""Delivery próprio (Etapa 22): taxa por bairro, entregas e acerto de motoboys.

Fica num modelo à parte (não em pos.order) porque o PDV carrega todos os campos do pedido.
"""

from odoo import _, api, fields, models
from odoo.exceptions import UserError

ESTADOS_ENTREGA = [("preparando", "Preparando"), ("saiu", "Saiu para entrega"), ("entregue", "Entregue"),
                   ("cancelada", "Cancelada")]


def _exigir_recurso(env):
    if not env.company.boteco_recurso_ativo("delivery_roteirizacao_motoboy"):
        raise UserError(_("O delivery está desligado na Central de Recursos."))


class BotecoDeliveryBairro(models.Model):
    _name = "boteco.delivery.bairro"
    _description = "Bairro atendido pelo delivery"
    _order = "name"

    name = fields.Char("Bairro", required=True)
    taxa = fields.Monetary("Taxa de entrega", currency_field="currency_id")
    tempo_estimado_min = fields.Integer("Tempo estimado (min)", default=40)
    active = fields.Boolean(default=True)
    company_id = fields.Many2one("res.company", default=lambda s: s.env.company, required=True)
    currency_id = fields.Many2one(related="company_id.currency_id")

    _sql_constraints = [("nome_unico", "unique(name, company_id)", "Este bairro já está cadastrado.")]


class BotecoDeliveryEntrega(models.Model):
    _name = "boteco.delivery.entrega"
    _description = "Entrega (delivery)"
    _order = "create_date desc"
    _rec_name = "order_id"

    order_id = fields.Many2one("pos.order", string="Pedido", required=True, ondelete="cascade", index=True)
    data = fields.Datetime(related="order_id.date_order", store=True)
    cliente_id = fields.Many2one(related="order_id.partner_id", string="Cliente", store=True)
    endereco = fields.Char("Endereço")
    bairro_id = fields.Many2one("boteco.delivery.bairro", string="Bairro")
    taxa = fields.Monetary("Taxa de entrega", currency_field="currency_id")
    motoboy_id = fields.Many2one("res.partner", string="Motoboy", domain=[("boteco_motoboy", "=", True)], index=True)
    estado = fields.Selection(ESTADOS_ENTREGA, default="preparando", required=True)
    saiu_em = fields.Datetime(readonly=True)
    entregue_em = fields.Datetime(readonly=True)
    company_id = fields.Many2one(related="order_id.company_id", store=True)
    currency_id = fields.Many2one(related="order_id.currency_id")

    @api.onchange("bairro_id")
    def _onchange_bairro_id(self):
        if self.bairro_id:
            self.taxa = self.bairro_id.taxa

    @api.model_create_multi
    def create(self, vals_list):
        _exigir_recurso(self.env)
        Bairro = self.env["boteco.delivery.bairro"]
        for vals in vals_list:
            if vals.get("bairro_id") and "taxa" not in vals:
                vals["taxa"] = Bairro.browse(vals["bairro_id"]).taxa
        return super().create(vals_list)

    def write(self, vals):
        agora = fields.Datetime.now()
        if vals.get("estado") == "saiu":
            vals.setdefault("saiu_em", agora)
        if vals.get("estado") == "entregue":
            vals.setdefault("entregue_em", agora)
        return super().write(vals)

    def action_saiu(self):
        self.write({"estado": "saiu"})

    def action_entregue(self):
        self.write({"estado": "entregue"})


class BotecoDeliveryAcerto(models.TransientModel):
    _name = "boteco.delivery.acerto"
    _description = "Acerto de motoboys"

    # Dia de operação (a noite que passa da meia-noite conta no dia em que começou)
    data_inicio = fields.Date("De", default=lambda s: s.env.company.boteco_dia_operacao(), required=True)
    data_fim = fields.Date("Até", default=lambda s: s.env.company.boteco_dia_operacao(), required=True)
    linha_ids = fields.One2many("boteco.delivery.acerto.linha", "acerto_id", string="Motoboys")

    def action_calcular(self):
        self.ensure_one()
        _exigir_recurso(self.env)
        company = self.env.company
        inicio, _f = company.boteco_intervalo_dia(self.data_inicio)
        _i, fim = company.boteco_intervalo_dia(self.data_fim)
        entregas = self.env["boteco.delivery.entrega"].search([
            ("company_id", "=", company.id), ("estado", "=", "entregue"), ("motoboy_id", "!=", False),
            ("entregue_em", ">=", inicio), ("entregue_em", "<", fim)])
        por_motoboy = {}
        for entrega in entregas:
            item = por_motoboy.setdefault(entrega.motoboy_id, {"entregas": 0, "taxas": 0.0})
            item["entregas"] += 1
            item["taxas"] += entrega.taxa
        self.linha_ids = [fields.Command.clear()] + [
            fields.Command.create({"motoboy_id": m.id, "entregas": d["entregas"], "total_taxas": d["taxas"]})
            for m, d in sorted(por_motoboy.items(), key=lambda kv: kv[0].name or "")
        ]
        return {"type": "ir.actions.act_window", "res_model": self._name, "res_id": self.id, "view_mode": "form",
                "target": "new"}


class BotecoDeliveryAcertoLinha(models.TransientModel):
    _name = "boteco.delivery.acerto.linha"
    _description = "Acerto por motoboy"

    acerto_id = fields.Many2one("boteco.delivery.acerto", required=True, ondelete="cascade")
    motoboy_id = fields.Many2one("res.partner", string="Motoboy")
    entregas = fields.Integer("Entregas")
    total_taxas = fields.Float("Taxas a repassar", digits=(16, 2))


class ResPartner(models.Model):
    _inherit = "res.partner"

    boteco_motoboy = fields.Boolean("É motoboy", help="Aparece na escolha de motoboy das entregas.")
    boteco_aniversario = fields.Date("Aniversário", help="Usado na régua de aniversariantes.")
