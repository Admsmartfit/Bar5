from odoo import http
from odoo.http import request


class BotecoContagemController(http.Controller):
    @http.route("/boteco/contagem/<int:contagem_id>", type="http", auth="user", sitemap=False)
    def tela(self, contagem_id, **kw):
        contagem = request.env["boteco.contagem"].browse(contagem_id).exists()
        if not contagem:
            return request.not_found()
        return request.render("boteco_estoque.tela_contagem", {"contagem": contagem})

    @http.route("/boteco/contagem/<int:contagem_id>/dados", type="json", auth="user")
    def dados(self, contagem_id):
        return request.env["boteco.contagem"].browse(contagem_id).boteco_dados_tela()

    @http.route("/boteco/contagem/<int:contagem_id>/salvar", type="json", auth="user")
    def salvar(self, contagem_id, contagens, terminar=False):
        contagem = request.env["boteco.contagem"].browse(contagem_id)
        contagem.boteco_salvar(contagens)
        if terminar:
            contagem.action_terminar()
        return {"ok": True}
