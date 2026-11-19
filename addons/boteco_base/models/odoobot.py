"""Etapa 32: OdooBot desligado e escondido (a ajuda rápida o substitui).

Não desinstala o módulo ``mail_bot`` (há relatos de instalação quebrada ao desinstalar):
só grava ``odoobot_state = disabled`` para todos e tira a conversa com ele da lista.
Funciona com ou sem o ``mail_bot`` instalado.
"""

from odoo import api, fields, models


class ResUsers(models.Model):
    _inherit = "res.users"

    @api.model_create_multi
    def create(self, vals_list):
        if "odoobot_state" in self._fields:
            for vals in vals_list:
                vals["odoobot_state"] = "disabled"
        return super().create(vals_list)

    @api.model
    def _boteco_desligar_odoobot(self):
        usuarios = self.sudo().with_context(active_test=False).search([])
        if "odoobot_state" in self._fields:
            usuarios.filtered(lambda u: u.odoobot_state != "disabled").write({"odoobot_state": "disabled"})
        bot = self.env.ref("base.partner_root", raise_if_not_found=False)
        if bot and "discuss.channel.member" in self.env:
            Membro = self.env["discuss.channel.member"].sudo()
            conversas = Membro.search([("partner_id", "=", bot.id), ("channel_id.channel_type", "=", "chat")]).channel_id
            # Desafixa a conversa com o OdooBot da lista de cada pessoa (volta só se ele mandar algo novo)
            Membro.search([("channel_id", "in", conversas.ids), ("partner_id", "!=", bot.id),
                           ("unpin_dt", "=", False)]).write({"unpin_dt": fields.Datetime.now()})
        return True
