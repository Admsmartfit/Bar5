from odoo import models


class ResUsers(models.Model):
    _inherit = "res.users"

    def _boteco_url_inicio(self):
        """Cozinheiro cai direto na tela de produção do dia."""
        self.ensure_one()
        if self.boteco_perfil_id.codigo == "cozinheiro":
            return "/odoo/action-boteco_cozinha_central.action_tela_producao"
        return super()._boteco_url_inicio()
