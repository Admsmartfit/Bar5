from odoo import fields, models


class AccountMove(models.Model):
    _inherit = "account.move"

    # Contas a pagar também podem ser de uma frente (ou "geral", rateada na DRE)
    boteco_frente = fields.Selection(selection_add=[("geral", "Geral (rateio)")], ondelete={"geral": "set null"})

