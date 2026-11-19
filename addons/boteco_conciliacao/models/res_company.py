from odoo import fields, models


class ResCompany(models.Model):
    _inherit = "res.company"

    # Central de Recursos (Etapa 28)
    boteco_flag_conciliacao_cartoes = fields.Boolean("Conferência de cartões e Pix (repasses e taxas)", default=True)
