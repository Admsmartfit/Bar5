from odoo import _, api, models


class BotecoSaude(models.AbstractModel):
    _inherit = "boteco.saude"

    @api.model
    def _verificacoes_extras(self):
        itens = super()._verificacoes_extras()
        pendentes = self.env["boteco.impressao.job"].sudo().search_count([("estado", "=", "esperando")])
        itens.append(self._item(
            _("Fila de impressão"),
            True,
            _("Nenhum ticket esperando.") if not pendentes else _("%s ticket(s) esperando a impressora voltar.", pendentes),
            alerta=pendentes > 0,
        ))
        return itens
