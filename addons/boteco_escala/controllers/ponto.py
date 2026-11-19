from odoo import _, http
from odoo.exceptions import UserError
from odoo.http import request

from odoo.addons.boteco_base.tools.rede import ip_na_rede


class BotecoPontoTela(http.Controller):
    """Tablet da entrada: a pessoa toca no nome e digita o PIN (entrada ou saída)."""

    def _na_rede(self, company):
        ip = request.httprequest.remote_addr
        return ip_na_rede(ip, company.boteco_rede_clientes) or ip_na_rede(ip, company.boteco_rede_sistema, vazio_libera=False)

    @http.route("/boteco/ponto", type="http", auth="public", methods=["GET", "POST"], sitemap=False)
    def ponto(self, user_id=None, pin=None, **kw):
        company = request.env.company.sudo()
        valores = {"titulo": _("Ponto – %s", company.name), "tema": "claro", "empresa": company,
                   "ligado": company.boteco_recurso_ativo("ponto_pin"),
                   "pessoas": request.env["res.users"].sudo().boteco_usuarios_pin(), "mensagem": None, "erro": None}
        if request.httprequest.method == "POST" and valores["ligado"]:
            user = request.env["res.users"].sudo().browse(int(user_id or 0)).exists()
            if not user or user.share or not user.boteco_perfil_id:
                valores["erro"] = _("Escolha o seu nome.")
            else:
                try:
                    r = request.env["boteco.ponto"].sudo().bater(user, pin, ip=request.httprequest.remote_addr,
                                                                 na_rede=self._na_rede(company))
                    valores["mensagem"] = (_("%(n)s: entrada às %(h)s. Bom trabalho!", n=r["nome"], h=r["hora"])
                                           if r["tipo"] == "entrada" else
                                           _("%(n)s: saída às %(h)s. Até a próxima!", n=r["nome"], h=r["hora"]))
                except UserError as erro:
                    valores["erro"] = erro.args[0]
        return request.render("boteco_escala.tela_ponto", valores)
