from odoo import api, models

MENUS_QR = ("boteco_autoatendimento.menu_boteco_tablets", "boteco_autoatendimento.menu_boteco_celulares")


class ResCompany(models.Model):
    _inherit = "res.company"

    def write(self, vals):
        res = super().write(vals)
        if "boteco_flag_autoatendimento_qr" in vals:
            self.env["res.company"]._boteco_aplicar_autoatendimento()
        return res

    @api.model
    def _boteco_aplicar_autoatendimento(self):
        """Bar sem QR/tablet (entrevista dos Primeiros passos): os menus somem; os dados ficam guardados."""
        ligado = any(c.boteco_flag_autoatendimento_qr for c in self.sudo().search([]))
        for xmlid in MENUS_QR:
            menu = self.env.ref(xmlid, raise_if_not_found=False)
            if menu and menu.active != ligado:
                menu.sudo().active = ligado
        return True
