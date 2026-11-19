import logging

from werkzeug.exceptions import Unauthorized

from odoo import _, fields, http
from odoo.exceptions import UserError
from odoo.http import request
from odoo.tools import consteq

from odoo.addons.boteco_base.tools.rede import ip_na_rede
from odoo.addons.pos_self_order.controllers.orders import PosSelfOrderController

_logger = logging.getLogger(__name__)

COOKIE = "boteco_disp"
COOKIE_IDADE = 60 * 60 * 12  # 12 horas: uma noite
COOKIE_MODO = "boteco_modo"
# Botões de chamada qualificada do tablet (lista fechada: o tablet não manda texto livre)
MOTIVOS_CHAMADA = {
    "copos_gelo": "trazer copos / gelo",
    "guardanapos": "trazer guardanapos",
    "conta_cartao": "conta no CARTÃO (levar a maquininha)",
    "conta_pix": "conta no PIX",
}


def _config_e_mesa(access_token, table_identifier):
    config = request.env["pos.config"].sudo().search([("access_token", "=", access_token)], limit=1)
    if not config or not access_token or not consteq(config.access_token, access_token):
        raise Unauthorized(_("Cardápio inválido."))
    mesa = request.env["restaurant.table"].sudo().search([("identifier", "=", table_identifier)], limit=1) \
        if table_identifier else request.env["restaurant.table"]
    return config, mesa


def _dispositivo_do_cookie(mesa):
    token = request.httprequest.cookies.get(COOKIE)
    if not token or not mesa:
        return request.env["boteco.dispositivo"].sudo()
    return request.env["boteco.dispositivo"].sudo().search(
        [("token", "=", token), ("mesa_id", "=", mesa.id), ("active", "=", True)], limit=1)


def _na_rede_do_bar(config, dispositivo=None):
    if dispositivo and dispositivo.tipo == "tablet":
        return True
    if not config.boteco_exigir_rede:
        return True
    empresa = config.company_id
    ip = request.httprequest.remote_addr
    return ip_na_rede(ip, empresa.boteco_rede_clientes) or ip_na_rede(ip, empresa.boteco_rede_sistema, vazio_libera=False)


def _modo_bebidas(config):
    """QR expresso de bebidas (Etapa 36): o 2º QR da mesa marca o modo num cookie (o pedido não leva campos extras)."""
    return (request.httprequest.cookies.get(COOKIE_MODO) == "bebidas"
            and config.company_id.boteco_recurso_ativo("qr_bebidas"))


def _resposta(dados, token=None):
    resposta = request.make_json_response(dados)
    if token:
        resposta.set_cookie(COOKIE, token, max_age=COOKIE_IDADE, httponly=True, samesite="Lax",
                            secure=request.httprequest.scheme == "https")
    return resposta


class BotecoMesaController(http.Controller):
    @http.route("/boteco/mesa/entrar", type="http", auth="public", methods=["POST"], csrf=False, website=False)
    def entrar(self, **kw):
        dados = request.get_json_data()
        config, mesa = _config_e_mesa(dados.get("access_token"), dados.get("table_identifier"))
        if not mesa:
            return _resposta({"estado": "sem_mesa"})
        tablet_token = dados.get("tablet_token")
        Dispositivo = request.env["boteco.dispositivo"].sudo()
        if tablet_token:
            tablet = Dispositivo.search([("token", "=", tablet_token), ("tipo", "=", "tablet"), ("active", "=", True)], limit=1)
            if not tablet or tablet.mesa_id != mesa:
                return _resposta({"estado": "tablet_invalido"})
            return _resposta({**tablet._dados(), **self._mesa(mesa, config)}, token=tablet.token)
        dispositivo = _dispositivo_do_cookie(mesa)
        if not _na_rede_do_bar(config, dispositivo):
            return _resposta({"estado": "fora_da_rede", **self._mesa(mesa, config)})
        novo_token = None
        if not dispositivo:
            dispositivo = Dispositivo.create({
                "tipo": "celular", "mesa_id": mesa.id, "estado": "pendente",
                "ip": request.httprequest.remote_addr,
                "navegador": (request.httprequest.user_agent.string or "")[:200],
                "company_id": config.company_id.id,
            })
            novo_token = dispositivo.token
        return _resposta({**dispositivo._dados(), **self._mesa(mesa, config)}, token=novo_token)

    def _mesa(self, mesa, config):
        return {
            "mesa_id": mesa.id,
            "mesa": mesa.table_number,
            "mesa_aberta": mesa._boteco_mesa_aberta(),
            "chamou_garcom": mesa.boteco_chamou_garcom,
            "pediu_conta": mesa.boteco_pediu_conta,
            "maior18_confirmado": mesa.boteco_maior18_confirmado,
            "limite_qr": config.boteco_limite_qr,
            "descanso_segundos": config.boteco_descanso_segundos or 120,
            "qr_bebidas_ativo": config.company_id.boteco_recurso_ativo("qr_bebidas"),
            # Central de Recursos: só o que o tablet precisa saber
            "recursos": {
                codigo: config.company_id.boteco_recurso_ativo(codigo)
                for codigo in ("tablet_neutro_anti_burst", "tablet_chamada_qualificada")
            },
        }

    @http.route("/boteco/mesa/solicitar", type="json", auth="public", csrf=False, website=False)
    def solicitar(self, access_token, table_identifier):
        """Primeiro pedido do celular: avisa o garçom para liberar com um toque."""
        config, mesa = _config_e_mesa(access_token, table_identifier)
        dispositivo = _dispositivo_do_cookie(mesa)
        if not dispositivo:
            return {"estado": "sem_dispositivo"}
        if not _na_rede_do_bar(config, dispositivo):
            return {"estado": "fora_da_rede"}
        if dispositivo._valido():
            return dispositivo._dados()
        if dispositivo.estado != "pendente" or dispositivo.codigo_sessao != mesa.boteco_codigo_sessao:
            dispositivo.write({"estado": "pendente"})
        for cfg in mesa.floor_id.pos_config_ids:
            if cfg.current_session_id:
                cfg._notify("BOTECO_APROVAR", {"id": dispositivo.id, "mesa": mesa.table_number, "mesa_id": mesa.id})
        return dispositivo._dados()

    @http.route("/boteco/mesa/status", type="json", auth="public", csrf=False, website=False)
    def status(self, access_token, table_identifier):
        config, mesa = _config_e_mesa(access_token, table_identifier)
        if not mesa:
            return {"estado": "sem_mesa"}
        dispositivo = _dispositivo_do_cookie(mesa)
        dados = {**(dispositivo._dados() if dispositivo else {"estado": "sem_dispositivo"}), **self._mesa(mesa, config)}
        Pedido = request.env["pos.order"].sudo()
        if dispositivo and dispositivo._valido():
            dados["conta"] = Pedido._boteco_resumo_mesa(mesa)
            dados["pedir_de_novo"] = Pedido._boteco_bebidas_da_mesa(mesa)
        if _modo_bebidas(config) and dispositivo and _na_rede_do_bar(config, dispositivo):
            dados["bebidas_mesa"] = Pedido._boteco_bebidas_mesa_ultimas(mesa)
            dados["mesa_aberta"] = mesa._boteco_mesa_aberta()
        return dados

    @http.route("/boteco/mesa/chamar", type="json", auth="public", csrf=False, website=False)
    def chamar(self, access_token, table_identifier, tipo="garcom", motivo=None):
        config, mesa = _config_e_mesa(access_token, table_identifier)
        dispositivo = _dispositivo_do_cookie(mesa)
        if not dispositivo or not _na_rede_do_bar(config, dispositivo):
            return {"ok": False, "erro": _("Conecte-se ao Wi-Fi do bar para chamar o garçom.")}
        if tipo == "conta":
            if not dispositivo._valido():
                return {"ok": False, "erro": _("Peça a conta ao garçom.")}
            mesa.boteco_marcar(pediu_conta=True)
        else:
            mesa.boteco_marcar(chamou_garcom=True)
        # Chamada qualificada (Etapa 16): o garçom já sabe o que levar
        texto = MOTIVOS_CHAMADA.get(motivo or "")
        if texto and config.company_id.boteco_recurso_ativo("tablet_chamada_qualificada"):
            for cfg in mesa.floor_id.pos_config_ids:
                if cfg.current_session_id:
                    cfg._notify("BOTECO_ALERTA", {"mensagem": _("Mesa %(m)s: %(t)s", m=mesa.table_number, t=texto),
                                                  "tipo": "chamada"})
        return {"ok": True}

    @http.route("/boteco/mesa/sair_quiosque", type="json", auth="public", csrf=False, website=False)
    def sair_quiosque(self, access_token, table_identifier, pin):
        """Tirar o tablet do modo quiosque: só com o PIN de quem tem a permissão."""
        _config_e_mesa(access_token, table_identifier)
        Tentativa = request.env["boteco.pin.tentativa"].sudo()
        publico = request.env.ref("base.public_user")
        if Tentativa._bloqueado(publico.id, "quiosque"):
            return {"ok": False, "erro": _("Muitos PINs errados. Espere 15 minutos.")}
        gerente = request.env["boteco.autorizacao"].sudo()._gerente_pelo_pin(pin, "pode_sair_quiosque")
        Tentativa._registrar_isolado(publico.id, "quiosque", bool(gerente), request.httprequest.remote_addr)
        if not gerente:
            return {"ok": False, "erro": _("PIN não confere.")}
        request.env["boteco.auditoria"].sudo().with_user(gerente).registrar(
            "quiosque", descricao=_("Tablet tirado do modo quiosque"), referencia=table_identifier)
        return {"ok": True}


class BotecoPosSelfOrderController(PosSelfOrderController):
    @http.route()
    def process_order_args(self, order, access_token, table_identifier, device_type, **kwargs):
        """Pedido do tablet/QR: confere aparelho liberado, rede do bar e limite de valor."""
        config, mesa = _config_e_mesa(access_token, table_identifier)
        dispositivo = _dispositivo_do_cookie(mesa) if mesa else request.env["boteco.dispositivo"].sudo()
        bebidas = bool(mesa) and _modo_bebidas(config)
        if config.self_ordering_mode == "mobile" and mesa:
            if not dispositivo or not _na_rede_do_bar(config, dispositivo):
                raise UserError(_("Conecte-se ao Wi-Fi do bar para pedir pelo celular."))
            if bebidas:
                # QR de bebidas: sem liberação do garçom, mas só com a mesa aberta (rede já conferida acima)
                if not mesa._boteco_mesa_aberta():
                    raise UserError(_("A mesa ainda não foi aberta. Peça ao garçom para abrir a mesa."))
            elif not dispositivo._valido():
                raise UserError(_("O garçom ainda não liberou este celular. Toque em 'Enviar pedido' e aguarde."))
        anterior = request.env["pos.order"].sudo().search([("uuid", "=", order.get("uuid"))], limit=1)
        total_anterior = anterior.amount_total if anterior else 0.0
        request.update_context(boteco_autoatendimento=True)
        resultado = super().process_order_args(order, access_token, table_identifier, device_type, **kwargs)
        if dispositivo:
            pedidos = request.env["pos.order"].sudo().browse([p["id"] for p in resultado.get("pos.order", [])])
            limite = config.boteco_limite_qr
            # O limite vale para cada envio (o que foi acrescentado agora), não para a conta inteira
            acrescimo = sum(pedidos.mapped("amount_total")) - total_anterior
            if bebidas and not all(p._boteco_so_bebidas_novas() for p in pedidos):
                if not dispositivo._valido():
                    raise UserError(_("Pelo QR de bebidas dá para pedir só bebidas. Para comida, use o QR do cardápio."))
                bebidas = False  # celular já liberado pediu comida junto: valem as regras normais
            if dispositivo.tipo == "celular" and limite and acrescimo > limite and not bebidas:
                raise UserError(_("Pedido acima de R$ %.2f pelo celular: chame o garçom.") % limite)
            pedidos._boteco_pos_autoatendimento(dispositivo, modo="bebidas" if bebidas else None)
            resultado = self._generate_return_values(pedidos, config)
        return resultado
