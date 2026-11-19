from odoo import _, fields, models

from .cotacao import ROTA


class BotecoCotacoesConfig(models.TransientModel):
    """Compras › Integração de cotações: endereço e token para configurar no serviço externo (n8n)."""

    _name = "boteco.cotacoes.config"
    _description = "Integração de cotações (API)"

    endereco = fields.Char("Endereço da API", readonly=True,
                           default=lambda s: s.env["ir.config_parameter"].sudo().get_param("web.base.url", "") + ROTA)
    token = fields.Char("Token (chave de acesso)", readonly=True, default=lambda s: s.env["boteco.cotacoes"]._token())
    ultima_chamada = fields.Char("Última chamada recebida", readonly=True, default=lambda s: s._ultima())

    def _ultima(self):
        log = self.env["boteco.cotacao.log"].sudo().search([], limit=1)
        if not log:
            return _("nenhuma ainda")
        return "%s · %s · %s" % (fields.Datetime.context_timestamp(self, log.create_date).strftime("%d/%m %H:%M"),
                                 dict(log._fields["resultado"].selection).get(log.resultado), log.detalhe or "")

    def action_trocar_token(self):
        self.env["boteco.cotacoes"].trocar_token()
        return {"type": "ir.actions.act_window", "res_model": self._name, "view_mode": "form", "target": "new",
                "name": _("Integração de cotações")}
