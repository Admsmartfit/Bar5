from odoo import fields, models


class PosPaymentMethod(models.Model):
    _inherit = "pos.payment.method"

    boteco_taxa_pct = fields.Float("Taxa da maquininha (%)", help="Ex.: débito 1,2%, crédito 3,1%, PIX 0%. Entra como despesa na DRE.")
    boteco_dias_recebimento = fields.Integer("Dias para cair na conta", default=1,
                                             help="Usado no fluxo de caixa previsto (crédito costuma ser 30 dias).")
