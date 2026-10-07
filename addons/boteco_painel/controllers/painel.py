from odoo import http
from odoo.http import request


class BotecoPainelController(http.Controller):
    @http.route("/boteco/painel/dados", type="json", auth="user")
    def dados(self):
        if not request.env.user.boteco_pode("pode_ver_financeiro"):
            return {"erro": "sem permissão"}
        return request.env["boteco.painel"].dados()
