from odoo import fields, models


class PurchaseOrder(models.Model):
    _inherit = "purchase.order"

    boteco_chave_nfe = fields.Char("Chave da NF-e", copy=False, index=True, readonly=True)

    _sql_constraints = [
        ("boteco_chave_nfe_unica", "unique(boteco_chave_nfe, company_id)",
         "Esta nota fiscal já foi importada."),
    ]
