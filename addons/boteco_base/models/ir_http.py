from odoo import models


class IrHttp(models.AbstractModel):
    _inherit = "ir.http"

    def session_info(self):
        """A tela recebe a aparência escolhida pela pessoa já na abertura (sem piscar)."""
        info = super().session_info()
        user = self.env.user
        if user and not user._is_public():
            info["boteco_aparencia"] = user.sudo().boteco_aparencia()
            info["boteco_ajuda_rapida"] = self.env.company.boteco_recurso_ativo("ajuda_rapida")
        return info
