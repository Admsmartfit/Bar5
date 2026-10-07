from odoo import api, fields, models


class BotecoAgendaMusica(models.Model):
    """Dias de música ao vivo: nesses dias o couvert artístico entra na conta por pessoa."""

    _name = "boteco.agenda.musica"
    _description = "Agenda de música (couvert)"
    _order = "data desc"

    data = fields.Date("Dia", required=True, index=True, help="Dia de operação (vira às 6h).")
    artista = fields.Char("Artista / atração")
    valor_couvert = fields.Monetary("Couvert por pessoa", required=True, default=10.0, currency_field="currency_id")
    company_id = fields.Many2one("res.company", default=lambda s: s.env.company, required=True)
    currency_id = fields.Many2one(related="company_id.currency_id")
    observacao = fields.Char("Observação")

    _sql_constraints = [
        ("dia_unico", "unique(data, company_id)", "Já existe música marcada para este dia."),
    ]

    @api.model
    def _couvert_do_dia(self, company=None, momento=None):
        """Registro da agenda do dia de operação atual (ou vazio)."""
        company = company or self.env.company
        dia = company.boteco_dia_operacao(momento)
        return self.sudo().search([("data", "=", dia), ("company_id", "=", company.id)], limit=1)
