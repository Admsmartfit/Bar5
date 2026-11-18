from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class ResCompany(models.Model):
    _inherit = "res.company"

    boteco_meta_clientes_noite = fields.Integer("Meta: clientes por noite", default=86,
                                                help="Ponto de equilíbrio do plano de negócios.")
    boteco_meta_kg_b2b_mes = fields.Float("Meta: kg vendidos a bares no mês", default=400.0)
    boteco_meta_bares_assessoria = fields.Integer("Meta: bares com assessoria", default=5)
    # Etapa 23: rateio da taxa de serviço (soma 100%)
    boteco_rateio_garcom_pct = fields.Float("Rateio da taxa: garçons (%)", default=70.0)
    boteco_rateio_producao_pct = fields.Float("Rateio da taxa: cozinha/bar (%)", default=20.0)
    boteco_rateio_casa_pct = fields.Float("Rateio da taxa: casa (%)", default=10.0)

    @api.constrains("boteco_rateio_garcom_pct", "boteco_rateio_producao_pct", "boteco_rateio_casa_pct")
    def _check_boteco_rateio(self):
        for company in self:
            partes = (company.boteco_rateio_garcom_pct, company.boteco_rateio_producao_pct, company.boteco_rateio_casa_pct)
            if any(p < 0 for p in partes) or abs(sum(partes) - 100.0) > 0.01:
                raise ValidationError(_("O rateio da taxa de serviço precisa somar 100%."))
