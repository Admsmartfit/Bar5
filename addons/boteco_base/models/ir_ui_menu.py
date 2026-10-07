from odoo import api, models, tools


class IrUiMenu(models.Model):
    _inherit = "ir.ui.menu"

    @api.model
    @tools.ormcache("frozenset(self.env.user.groups_id.ids)", "debug")
    def _visible_menu_ids(self, debug=False):
        """Esconde os menus que o perfil do boteco não usa ("uma tela, um trabalho").

        O cache é por conjunto de grupos; como cada perfil tem seu grupo, pessoas de
        perfis diferentes nunca compartilham o mesmo resultado.
        """
        visiveis = super()._visible_menu_ids(debug)
        perfil = self.env.user.boteco_perfil_id
        if not perfil or not perfil.menu_ids or self.env.user._is_superuser():
            return visiveis
        raizes = set(perfil.menu_ids.ids)
        menus = self.sudo().browse(visiveis)
        permitidos = set()
        for menu in menus:
            raiz = int((menu.parent_path or str(menu.id)).split("/")[0])
            if raiz in raizes:
                permitidos.add(menu.id)
        return frozenset(permitidos)
