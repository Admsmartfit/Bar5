"""Validador de saída na portaria (Etapa 20): bipa a comanda/QR e vê VERDE (paga) ou VERMELHO (pendente)."""

from odoo import _, http
from odoo.http import request


class BotecoPortaria(http.Controller):
    @http.route("/boteco/portaria", type="http", auth="user", website=False)
    def tela(self, **kw):
        ativo = request.env.company.boteco_recurso_ativo("portaria_validador_saida")
        return request.render("boteco_pos.portaria_tela", {"ativo": ativo})

    @http.route("/boteco/portaria/validar", type="json", auth="user", website=False)
    def validar(self, codigo):
        company = request.env.company
        if not company.boteco_recurso_ativo("portaria_validador_saida"):
            return {"cor": "cinza", "titulo": _("Recurso desligado"),
                    "detalhe": _("Ligue 'Validador de saída na portaria' na Central de Recursos.")}
        return request.env["pos.order"].boteco_validar_saida(codigo)
