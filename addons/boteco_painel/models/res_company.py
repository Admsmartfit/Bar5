from odoo import fields, models


class ResCompany(models.Model):
    _inherit = "res.company"

    boteco_meta_clientes_noite = fields.Integer("Meta: clientes por noite", default=86,
                                                help="Ponto de equilíbrio do plano de negócios.")
    boteco_meta_kg_b2b_mes = fields.Float("Meta: kg vendidos a bares no mês", default=400.0)
    boteco_meta_bares_assessoria = fields.Integer("Meta: bares com assessoria", default=5)
