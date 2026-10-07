from odoo import models


class ResUsers(models.Model):
    _inherit = "res.users"

    def _boteco_url_inicio(self):
        """Dono cai direto no painel."""
        self.ensure_one()
        if self.boteco_perfil_id.codigo == "dono" or self._is_admin():
            return "/odoo/action-boteco_painel.action_painel_dono"
        return super()._boteco_url_inicio()
