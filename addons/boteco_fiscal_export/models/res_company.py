from odoo import fields, models


class ResCompany(models.Model):
    _inherit = "res.company"

    boteco_fiscal_dias_alerta = fields.Integer(
        "Alertar vendas sem nota há mais de (dias)", default=3,
        help="Confirme o prazo com o contador: no varejo a NFC-e normalmente é emitida no momento da venda.")
