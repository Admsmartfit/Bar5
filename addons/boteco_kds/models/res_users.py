from odoo import models


class ResUsers(models.Model):
    _inherit = "res.users"

    def _boteco_url_inicio(self):
        """Chapeiro cai direto na fila da chapa; gerente no painel de produção."""
        self.ensure_one()
        if self.boteco_perfil_id.codigo == "chapeiro":
            return "/odoo/action-boteco_kds.action_kds_chapa"
        return super()._boteco_url_inicio()
