from odoo import _, api, models


class BotecoPainel(models.AbstractModel):
    _inherit = "boteco.painel"

    @api.model
    def _alertas_extras(self, company):
        alertas = super()._alertas_extras(company)
        antigos = self.env["boteco.fiscal.registro"].sudo().pendentes_antigos(company)
        if antigos:
            alertas.append(_("%(n)s venda(s) sem nota há mais de %(d)s dias (R$ %(v).2f). Exporte e emita.",
                             n=len(antigos), d=company.boteco_fiscal_dias_alerta, v=sum(antigos.mapped("valor_total"))))
        return alertas
