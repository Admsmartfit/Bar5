from odoo import fields, models

FRENTES = [("bar", "Bar"), ("b2b", "Tira-gosto B2B"), ("assessoria", "Assessoria")]


class AccountMove(models.Model):
    _inherit = "account.move"

    boteco_frente = fields.Selection(
        FRENTES, string="Frente do negócio", index=True,
        help="Usado na DRE por frente (bar, tira-gosto vendido a outros bares, assessoria).",
    )
    boteco_contrato_id = fields.Many2one("boteco.contrato.assessoria", string="Contrato de assessoria",
                                         readonly=True, index="btree_not_null")
    boteco_competencia = fields.Date("Competência", readonly=True, help="Mês a que a mensalidade se refere.")
