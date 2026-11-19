"""API de cotações (19/11/2026): o serviço externo (n8n + Evolution API + IA) manda só dados limpos.

    POST /api/boteco/webhook/cotacao_recebida
    Authorization: Bearer <token>       (ou o cabeçalho X-API-Key: <token>)
    Content-Type: application/json

    {"id_fornecedor": "atacadao", "id_produto_interno": "CERV-600", "unidade_medida": "cx",
     "quantidade_embalagem": 24, "preco_cotado": 189.90, "descricao": "Brahma 600ml cx c/24", "referencia": "wa:ABC123"}
    ou só com nome e telefone: {"telefone_origem": "5528999991234", "produto_nome_bruto": "Alcatra Grill",
                               "unidade_medida": "kg", "preco_cotado": 49.9, "condicao_promocional": "leve 4 pague 3",
                               "link_comprovante": "https://.../encarte.jpg"}
    ou {"cotacoes": [ {...}, {...} ]}

Respostas: 200 com o resultado de cada item | 401 token | 400 JSON inválido | 429 limite por minuto | 503 desligado.
"""

import ipaddress
import json
import logging

from odoo import http
from odoo.http import request
from odoo.tools import consteq

from ..models.cotacao import PARAM_TOKEN, ROTA

_logger = logging.getLogger(__name__)


def _rede_interna(ip):
    try:
        endereco = ipaddress.ip_address(ip or "")
    except ValueError:
        return False
    return endereco.is_private or endereco.is_loopback


class BotecoCotacoesApi(http.Controller):
    def _json(self, dados, status=200):
        return request.make_json_response(dados, status=status)

    def _token_recebido(self):
        cabecalhos = request.httprequest.headers
        auth = cabecalhos.get("Authorization", "")
        if auth.lower().startswith("bearer "):
            return auth[7:].strip()
        return (cabecalhos.get("X-API-Key") or "").strip()

    @http.route(ROTA, type="http", auth="public", methods=["POST"], csrf=False, sitemap=False)
    def cotacao_recebida(self, **kw):
        Log = request.env["boteco.cotacao.log"].sudo()
        ip = request.httprequest.remote_addr
        # De fora da rede só por HTTPS (o n8n no mesmo servidor/rede pode usar HTTP interno)
        if request.httprequest.scheme != "https" and not _rede_interna(ip):
            Log.registrar("recusado", ip=ip, detalhe="sem HTTPS")
            return self._json({"ok": False, "erro": "use HTTPS"}, status=401)
        esperado = request.env["ir.config_parameter"].sudo().get_param(PARAM_TOKEN)
        recebido = self._token_recebido()
        if not esperado or not recebido or not consteq(esperado, recebido):
            Log.registrar("recusado", ip=ip, detalhe="token errado")
            return self._json({"ok": False, "erro": "token inválido"}, status=401)
        if Log._boteco_acima_do_limite():
            Log.registrar("limite", ip=ip)
            return self._json({"ok": False, "erro": "muitas chamadas por minuto"}, status=429)
        if not request.env.company.sudo().boteco_recurso_ativo("cotacoes_externas"):
            return self._json({"ok": False, "erro": "recebimento de cotações desligado na Central de Recursos"}, status=503)
        try:
            dados = json.loads(request.httprequest.get_data(as_text=True) or "{}")
            if not isinstance(dados, dict):
                raise ValueError
        except ValueError:
            Log.registrar("erro", ip=ip, detalhe="JSON inválido")
            return self._json({"ok": False, "erro": "JSON inválido"}, status=400)
        resultados = request.env["boteco.cotacoes"].sudo().receber(dados)
        aceitos = sum(1 for r in resultados if r.get("status") == "ok")
        Log.registrar("ok" if aceitos == len(resultados) else "parcial", ip=ip, itens=aceitos,
                      detalhe="%s de %s item(ns) aplicados" % (aceitos, len(resultados)))
        return self._json({"ok": True, "aplicados": aceitos, "resultados": resultados})
