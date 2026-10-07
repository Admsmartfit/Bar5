from odoo import http
from odoo.http import request

from ..models.boteco_perfil import CODIGOS_PERFIL


class BotecoAjudaController(http.Controller):
    @http.route(["/boteco/ajuda", "/boteco/ajuda/<string:perfil>"], type="http", auth="user", sitemap=False)
    def ajuda(self, perfil=None, **kw):
        """Guia de uma página por perfil (tour de 3 passos + tarefas principais)."""
        codigos = dict(CODIGOS_PERFIL)
        perfil = perfil or request.env.user.boteco_perfil_id.codigo or "garcom"
        if perfil not in codigos:
            perfil = "garcom"
        return request.render(
            "boteco_base.pagina_ajuda",
            {"perfil": perfil, "nome_perfil": codigos[perfil], "perfis": CODIGOS_PERFIL},
        )

    @http.route("/boteco/tour/visto", type="json", auth="user")
    def tour_visto(self):
        request.env.user.sudo().boteco_tour_visto = True
        return True
