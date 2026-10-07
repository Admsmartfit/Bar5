from odoo import http
from odoo.http import request


class BotecoSaudeController(http.Controller):
    @http.route("/boteco/saude", type="http", auth="user", website=False, sitemap=False)
    def saude(self, **kw):
        if not request.env.user.has_group("boteco_base.group_gerente"):
            return request.redirect("/boteco/inicio")
        dados = request.env["boteco.saude"].sudo().verificar()
        return request.render("boteco_base.pagina_saude", {"dados": dados})

    @http.route("/boteco/saude.json", type="http", auth="user", website=False, sitemap=False)
    def saude_json(self, **kw):
        if not request.env.user.has_group("boteco_base.group_gerente"):
            return request.make_json_response({"erro": "sem permissão"}, status=403)
        return request.make_json_response(request.env["boteco.saude"].sudo().verificar())

    @http.route("/boteco/impressora/<int:impressora_id>/teste", type="json", auth="user")
    def imprimir_teste(self, impressora_id):
        if not request.env.user.has_group("boteco_base.group_gerente"):
            return {"erro": "sem permissão"}
        impressora = request.env["boteco.impressora"].browse(impressora_id).exists()
        if not impressora:
            return {"erro": "Impressora não encontrada."}
        dados = impressora._ticket_teste() if impressora.linguagem == "escpos" else impressora._etiqueta_teste()
        ok = impressora.sudo().enviar_bytes(dados, levantar=False)
        return {"ok": ok, "mensagem": None if ok else impressora._mensagem_erro()}
