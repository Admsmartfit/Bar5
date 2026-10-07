import logging

from odoo import _, http
from odoo.exceptions import AccessDenied
from odoo.http import request

from ..tools.rede import ip_na_rede

_logger = logging.getLogger(__name__)


class BotecoPinController(http.Controller):
    def _rede_liberada(self):
        empresa = request.env["res.company"].sudo().search([], order="id", limit=1)
        return ip_na_rede(request.httprequest.remote_addr, empresa.boteco_rede_sistema)

    @http.route("/boteco/pin", type="http", auth="public", website=False, sitemap=False)
    def tela_pin(self, **kw):
        """Tela de entrada por PIN: escolhe o nome, digita o PIN, cai na tela do trabalho."""
        if not self._rede_liberada():
            return request.redirect("/web/login")
        pessoas = request.env["res.users"].sudo().boteco_usuarios_pin()
        empresa = request.env["res.company"].sudo().search([], order="id", limit=1)
        return request.render(
            "boteco_base.tela_pin",
            {"pessoas": pessoas, "empresa": empresa, "logado": request.session.uid},
        )

    @http.route("/boteco/pin/entrar", type="json", auth="public", website=False, csrf=False)
    def entrar(self, user_id, pin, **kw):
        if not self._rede_liberada():
            return {"erro": _("Entrada por PIN só pela rede do bar.")}
        user = request.env["res.users"].sudo().browse(int(user_id)).exists()
        if not user or user.share or not user.active:
            return {"erro": _("Pessoa não encontrada.")}
        credential = {"type": "boteco_pin", "login": user.login, "pin": str(pin or "")}
        try:
            request.session.logout(keep_db=True)
            request.session.authenticate(request.db, credential)
        except AccessDenied as erro:
            mensagem = erro.args[0] if erro.args else _("PIN errado.")
            if mensagem == "Access Denied":
                mensagem = _("PIN errado ou pessoa bloqueada. Chame o gerente.")
            return {"erro": mensagem}
        return {"ok": True, "url": "/boteco/inicio"}

    @http.route("/boteco/inicio", type="http", auth="user", website=False, sitemap=False)
    def inicio(self, **kw):
        """Cada perfil cai direto na tela do seu trabalho."""
        url = request.env.user._boteco_url_inicio() or "/odoo"
        return request.redirect(url, local=True)

    @http.route("/boteco/sair", type="http", auth="public", website=False, sitemap=False)
    def sair(self, **kw):
        """Troca de pessoa no aparelho compartilhado: sai e volta para a tela de PIN."""
        request.session.logout(keep_db=True)
        return request.redirect("/boteco/pin")
