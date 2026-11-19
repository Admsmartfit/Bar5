from odoo import _, api, fields, models

from .cotacao import PARAM_TOKEN_COLETOR, PARAM_TOKEN_WHATSAPP

DIAS = [("0", "Seg"), ("1", "Ter"), ("2", "Qua"), ("3", "Qui"), ("4", "Sex"), ("5", "Sáb"), ("6", "Dom")]


class BotecoCotacoesConfig(models.TransientModel):
    """Compras › WhatsApp e coletor: horários do coletor e os tokens das integrações (só o dono)."""

    _name = "boteco.cotacoes.config"
    _description = "Configuração das cotações automáticas"

    instagram_hora = fields.Char("Instagram: ler às", default=lambda s: s._p("boteco.instagram_hora", "08:00"))
    sites_hora = fields.Char("Sites: ler às", default=lambda s: s._p("boteco.coletor_sites_hora", "08:00"))
    sites_dias = fields.Char("Sites: dias (0=seg … 6=dom)", default=lambda s: s._p("boteco.coletor_sites_dias", "0,3"))
    token_whatsapp = fields.Char("Token do WhatsApp", readonly=True,
                                 default=lambda s: s.env["boteco.cotacoes"]._token(PARAM_TOKEN_WHATSAPP))
    token_coletor = fields.Char("Token do coletor", readonly=True,
                                default=lambda s: s.env["boteco.cotacoes"]._token(PARAM_TOKEN_COLETOR))
    coletor_visto_em = fields.Char("Coletor deu sinal em", readonly=True,
                                   default=lambda s: s._p("boteco.coletor_visto_em", "nunca"))

    @api.model
    def _p(self, nome, padrao):
        return self.env["ir.config_parameter"].sudo().get_param(nome, padrao)

    def action_salvar(self):
        self.ensure_one()
        Param = self.env["ir.config_parameter"].sudo()
        from odoo.addons.boteco_estoque.models.res_partner import hora_texto
        for campo, parametro in (("instagram_hora", "boteco.instagram_hora"), ("sites_hora", "boteco.coletor_sites_hora")):
            Param.set_param(parametro, hora_texto(self[campo]).strftime("%H:%M"))
        dias = ",".join(sorted({d.strip() for d in (self.sites_dias or "").split(",") if d.strip() in "0123456"}))
        Param.set_param("boteco.coletor_sites_dias", dias or "0,3")
        self.env["res.partner"]._boteco_agendar_monitor_instagram()
        return {"type": "ir.actions.client", "tag": "display_notification",
                "params": {"message": _("Horários salvos."), "type": "success", "next": {"type": "ir.actions.act_window_close"}}}

    def action_trocar_token_whatsapp(self):
        self.env["boteco.cotacoes"].trocar_token("whatsapp")
        return self._reabrir()

    def action_trocar_token_coletor(self):
        self.env["boteco.cotacoes"].trocar_token("coletor")
        return self._reabrir()

    def _reabrir(self):
        return {"type": "ir.actions.act_window", "res_model": self._name, "view_mode": "form", "target": "new",
                "name": _("WhatsApp e coletor")}
