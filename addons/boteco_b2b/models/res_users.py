from odoo import models


class ResUsers(models.Model):
    _inherit = "res.users"

    def _boteco_url_inicio(self):
        """Comercial cai direto nos pedidos de outros bares."""
        self.ensure_one()
        if self.boteco_perfil_id.codigo == "comercial":
            return "/odoo/action-boteco_b2b.action_pedidos_b2b"
        return super()._boteco_url_inicio()
