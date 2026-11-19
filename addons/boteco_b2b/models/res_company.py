from odoo import api, models


class ResCompany(models.Model):
    _inherit = "res.company"

    def write(self, vals):
        res = super().write(vals)
        if "boteco_flag_vendas_b2b" in vals:
            self.env["res.company"]._boteco_aplicar_b2b()
        return res

    @api.model
    def _boteco_aplicar_b2b(self):
        """Etapa 34: Venda a bares escondida quando a chave está desligada (os dados ficam guardados)."""
        ligado = any(c.boteco_flag_vendas_b2b for c in self.sudo().search([]))
        menu = self.env.ref("boteco_b2b.menu_boteco_b2b", raise_if_not_found=False)
        if menu and menu.active != ligado:
            menu.sudo().active = ligado
        return True
