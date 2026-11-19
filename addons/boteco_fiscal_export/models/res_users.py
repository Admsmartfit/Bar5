from odoo import models


class ResUsers(models.Model):
    _inherit = "res.users"

    def _boteco_url_inicio(self):
        """Etapa 34: o contador cai direto nas vendas e notas (Finanças › Fiscal)."""
        self.ensure_one()
        if self.boteco_perfil_id.codigo == "contador":
            return "/odoo/action-boteco_fiscal_export.action_fiscal"
        return super()._boteco_url_inicio()
