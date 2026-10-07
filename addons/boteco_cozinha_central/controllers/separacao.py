from odoo import _, http
from odoo.exceptions import UserError
from odoo.http import request


class BotecoSeparacaoController(http.Controller):
    """Separação lendo o QR da etiqueta (câmera do celular ou leitor USB/Bluetooth)."""

    @http.route("/boteco/separacao/<int:picking_id>", type="http", auth="user", sitemap=False)
    def tela(self, picking_id, **kw):
        picking = request.env["stock.picking"].browse(picking_id).exists()
        if not picking:
            return request.not_found()
        return request.render("boteco_cozinha_central.tela_separacao", {"picking": picking})

    @http.route("/boteco/separacao/<int:picking_id>/dados", type="json", auth="user")
    def dados(self, picking_id):
        return request.env["stock.picking"].browse(picking_id).boteco_dados_separacao()

    @http.route("/boteco/separacao/<int:picking_id>/ler", type="json", auth="user")
    def ler(self, picking_id, codigo):
        picking = request.env["stock.picking"].browse(picking_id)
        try:
            return {"ok": True, "mensagem": picking.boteco_ler_lote(codigo), **picking.boteco_dados_separacao()}
        except UserError as erro:
            return {"ok": False, "mensagem": erro.args[0], **picking.boteco_dados_separacao()}

    @http.route("/boteco/separacao/<int:picking_id>/concluir", type="json", auth="user")
    def concluir(self, picking_id):
        picking = request.env["stock.picking"].browse(picking_id)
        try:
            picking.boteco_concluir_separacao()
        except UserError as erro:
            return {"ok": False, "mensagem": erro.args[0]}
        return {"ok": True, "mensagem": _("Separação concluída.")}
