"""Página pública de reserva (link para Instagram/WhatsApp): sem login, com trava contra robô."""

from datetime import timedelta
from urllib.parse import quote

from odoo import _, fields, http
from odoo.exceptions import UserError
from odoo.http import request

from ..models.boteco_reserva import utc_para_local

LIMITE_POR_HORA = 5  # reservas pelo mesmo endereço de internet em 1 hora


class BotecoReservar(http.Controller):
    def _empresa(self):
        return request.env.company.sudo()

    def _pagina(self, template, **valores):
        company = self._empresa()
        return request.render(template, {"empresa": company, "titulo": _("Reservar mesa – %s", company.name),
                                         "tema": "claro", **valores})

    def _hoje(self, company):
        return utc_para_local(company, fields.Datetime.now()).date()

    @http.route("/reservar", type="http", auth="public", methods=["GET"], sitemap=False)
    def reservar(self, dia=None, pessoas=None, **kw):
        company = self._empresa()
        if not company.boteco_recurso_ativo("reservas_mesas"):
            return self._pagina("boteco_reservas.pagina_indisponivel")
        hoje = self._hoje(company)
        try:
            dia = max(fields.Date.to_date(dia), hoje) if dia else hoje
        except ValueError:
            dia = hoje
        pessoas = max(1, min(int(pessoas or 2) if str(pessoas or "2").isdigit() else 2, 50))
        faixas = request.env["boteco.reserva"].sudo().boteco_disponibilidade(company, dia, pessoas)
        return self._pagina("boteco_reservas.pagina_reservar", dia=dia, pessoas=pessoas, faixas=faixas,
                            hoje=hoje, ate=hoje + timedelta(days=60), erro=kw.get("erro"))

    @http.route("/reservar", type="http", auth="public", methods=["POST"], sitemap=False)
    def reservar_enviar(self, **dados):
        company = self._empresa()
        if not company.boteco_recurso_ativo("reservas_mesas"):
            return self._pagina("boteco_reservas.pagina_indisponivel")
        if dados.get("site"):  # campo escondido: só robô preenche
            return self._pagina("boteco_reservas.pagina_indisponivel")
        Reserva = request.env["boteco.reserva"].sudo()
        ip = request.httprequest.remote_addr
        recentes = Reserva.search_count([("ip", "=", ip), ("create_date", ">", fields.Datetime.now() - timedelta(hours=1))])
        if recentes >= LIMITE_POR_HORA:
            return self.reservar(dia=dados.get("dia"), pessoas=dados.get("pessoas"),
                                 erro=_("Muitas reservas seguidas deste aparelho. Fale com a gente pelo WhatsApp."))
        if not (dados.get("nome") or "").strip() or len("".join(c for c in dados.get("celular") or "" if c.isdigit())) < 10:
            return self.reservar(dia=dados.get("dia"), pessoas=dados.get("pessoas"),
                                 erro=_("Informe seu nome e o celular com DDD."))
        if dados.get("espera"):
            request.env["boteco.reserva.espera"].sudo().create({
                "nome": dados["nome"].strip()[:80], "celular": dados["celular"].strip()[:30],
                "dia": fields.Date.to_date(dados["dia"]), "faixa": dados.get("faixa") or False,
                "pessoas": int(dados.get("pessoas") or 2), "company_id": company.id,
            })
            return self._pagina("boteco_reservas.pagina_espera", nome=dados["nome"])
        try:
            reserva = Reserva.boteco_reservar(company, dados, origem="link", ip=ip)
        except (UserError, ValueError, KeyError) as erro:
            mensagem = erro.args[0] if isinstance(erro, UserError) else _("Confira os dados da reserva.")
            return self.reservar(dia=dados.get("dia"), pessoas=dados.get("pessoas"), erro=mensagem)
        return request.redirect("/reservar/%s" % reserva.token)

    def _por_token(self, token):
        if not token or len(token) < 16:
            return request.env["boteco.reserva"]
        return request.env["boteco.reserva"].sudo().search([("token", "=", token)], limit=1)

    @http.route("/reservar/<string:token>", type="http", auth="public", methods=["GET", "POST"], sitemap=False)
    def gerenciar(self, token, acao=None, **kw):
        reserva = self._por_token(token)
        if not reserva:
            return request.not_found()
        if request.httprequest.method == "POST":
            if acao == "cancelar":
                reserva.action_cancelar()
            elif acao == "confirmar" and reserva.estado == "confirmada":
                reserva.write({"lembrete_pendente": False})
            return request.redirect("/reservar/%s" % token)
        company = reserva.company_id
        pix = company._boteco_pix_sinal(reserva) if reserva.estado == "pendente" else ""
        return self._pagina("boteco_reservas.pagina_reserva", reserva=reserva, quando=reserva._boteco_quando(),
                            pix=pix, pix_qr=quote(pix, safe=""))
