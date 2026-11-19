"""Entradas das cotações: webhook do WhatsApp (Evolution API) e API do coletor externo. Sempre com token."""

import ipaddress
import json
import logging

from werkzeug.exceptions import Unauthorized

from odoo import http
from odoo.http import request
from odoo.tools import consteq

from ..models.cotacao import PARAM_TOKEN_COLETOR, PARAM_TOKEN_WHATSAPP

_logger = logging.getLogger(__name__)


def _rede_interna(ip):
    try:
        endereco = ipaddress.ip_address(ip or "")
    except ValueError:
        return False
    return endereco.is_private or endereco.is_loopback


class BotecoCotacoesApi(http.Controller):
    def _ip(self):
        return request.httprequest.remote_addr

    def _token_ok(self, parametro, recebido, canal):
        Log = request.env["boteco.cotacao.log"].sudo()
        # Só HTTPS de fora; dentro do servidor (contêineres na rede interna) pode ser HTTP
        if request.httprequest.scheme != "https" and not _rede_interna(self._ip()):
            Log.registrar(canal, "recusado", ip=self._ip(), detalhe="sem HTTPS")
            return False
        esperado = request.env["ir.config_parameter"].sudo().get_param(parametro)
        if not esperado or not recebido or not consteq(esperado, recebido):
            Log.registrar(canal, "recusado", ip=self._ip(), detalhe="token errado")
            return False
        if Log._boteco_acima_do_limite(canal, por_minuto=600 if canal == "whatsapp" else 60):
            Log.registrar(canal, "limite", ip=self._ip())
            return False
        return True

    def _json(self, dados, status=200):
        return request.make_json_response(dados, status=status)

    @http.route("/boteco/compras/whatsapp/<string:token>", type="http", auth="public", methods=["POST"], csrf=False,
                sitemap=False)
    def whatsapp(self, token, **kw):
        if not self._token_ok(PARAM_TOKEN_WHATSAPP, token, "whatsapp"):
            return self._json({"ok": False}, status=401)
        try:
            evento = json.loads(request.httprequest.get_data(as_text=True) or "{}")
        except ValueError:
            return self._json({"ok": False, "erro": "json"}, status=400)
        resultado = request.env["boteco.whatsapp"].sudo().receber(evento, ip=self._ip())
        return self._json({"ok": True, "resultado": resultado})

    def _bearer(self):
        cabecalho = request.httprequest.headers.get("Authorization", "")
        return cabecalho[7:].strip() if cabecalho.lower().startswith("bearer ") else ""

    @http.route("/boteco/compras/api/fontes", type="http", auth="public", methods=["GET"], csrf=False, sitemap=False)
    def fontes(self, **kw):
        if not self._token_ok(PARAM_TOKEN_COLETOR, self._bearer(), "coletor"):
            raise Unauthorized()
        if not request.env.company.sudo().boteco_recurso_ativo("coletor_ofertas"):
            return self._json({"fontes": [], "desligado": True})
        return self._json(request.env["boteco.cotacoes"].sudo().fontes())

    @http.route("/boteco/compras/api/cotacoes", type="http", auth="public", methods=["POST"], csrf=False, sitemap=False)
    def cotacoes(self, **kw):
        if not self._token_ok(PARAM_TOKEN_COLETOR, self._bearer(), "coletor"):
            return self._json({"ok": False}, status=401)
        if not request.env.company.sudo().boteco_recurso_ativo("coletor_ofertas"):
            return self._json({"ok": False, "desligado": True})
        try:
            dados = json.loads(request.httprequest.get_data(as_text=True) or "{}")
        except ValueError:
            return self._json({"ok": False, "erro": "json"}, status=400)
        total = request.env["boteco.cotacoes"].sudo().receber_do_coletor(dados)
        request.env["boteco.cotacao.log"].sudo().registrar("coletor", "ok", itens=total, ip=self._ip())
        return self._json({"ok": True, "itens": total})
