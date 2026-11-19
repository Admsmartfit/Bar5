from odoo import api, models


class ResCompany(models.Model):
    _inherit = "res.company"

    def write(self, vals):
        res = super().write(vals)
        if "boteco_tipo_unidade" in vals:
            self.env["res.company"]._boteco_aplicar_cozinha_central()
        return res

    @api.model
    def _boteco_aplicar_cozinha_central(self):
        """Bar que não produz em lote (entrevista dos Primeiros passos): o menu da cozinha central some."""
        ligado = any(c.boteco_tipo_unidade in ("bar_e_cozinha", "cozinha_central") for c in self.sudo().search([]))
        # Já usa a cozinha central (receitas de produção cadastradas)? Não esconde nada de surpresa.
        ligado = ligado or bool(self.env["mrp.bom"].sudo().search_count(
            [("product_tmpl_id.boteco_produzido_cozinha", "=", True)], limit=1))
        menu = self.env.ref("boteco_cozinha_central.menu_boteco_cozinha", raise_if_not_found=False)
        if menu and menu.active != ligado:
            menu.sudo().active = ligado
        return True
