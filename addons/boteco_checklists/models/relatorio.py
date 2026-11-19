from odoo import _, fields, models
from odoo.exceptions import UserError


class BotecoChecklistRelatorio(models.TransientModel):
    """PDF para a fiscalização: todos os checklists do período, com respostas, fotos e quem assinou."""

    _name = "boteco.checklist.relatorio"
    _description = "Relatório de boas práticas para a fiscalização"

    data_de = fields.Date("De", required=True, default=lambda s: fields.Date.context_today(s).replace(day=1))
    data_ate = fields.Date("Até", required=True, default=fields.Date.context_today)

    def action_imprimir(self):
        self.ensure_one()
        execucoes = self.env["boteco.checklist.execucao"].search(
            [("data", ">=", self.data_de), ("data", "<=", self.data_ate), ("company_id", "=", self.env.company.id)],
            order="data, hora_limite, id")
        if not execucoes:
            raise UserError(_("Nenhum checklist nesse período."))
        return self.env.ref("boteco_checklists.report_checklists").report_action(execucoes)
