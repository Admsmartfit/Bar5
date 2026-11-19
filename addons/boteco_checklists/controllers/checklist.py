import base64

from odoo import _, fields, http
from odoo.exceptions import UserError
from odoo.http import request


class BotecoChecklistTela(http.Controller):
    @http.route("/boteco/checklist", type="http", auth="user", sitemap=False)
    def lista(self, **kw):
        Execucao = request.env["boteco.checklist.execucao"]
        ligado = request.env.company.boteco_recurso_ativo("checklists_appcc")
        if ligado:
            Execucao.sudo()._cron_gerar()  # garante os de hoje (se o cron ainda não rodou)
        return request.render("boteco_checklists.tela_lista", {
            "titulo": _("Checklists do dia"), "tema": "claro", "ligado": ligado,
            "pendentes": Execucao.pendentes_para() if ligado else Execucao, "feito": kw.get("feito"),
            "hora": lambda quando: fields.Datetime.context_timestamp(request.env.user, quando).strftime("%H:%M")
            if quando else "—",
        })

    @http.route("/boteco/checklist/<int:execucao_id>", type="http", auth="user", methods=["GET", "POST"], sitemap=False)
    def fazer(self, execucao_id, **kw):
        execucao = request.env["boteco.checklist.execucao"].browse(execucao_id)
        if not execucao.exists() or execucao not in request.env["boteco.checklist.execucao"].pendentes_para():
            return request.redirect("/boteco/checklist")
        erro = None
        if request.httprequest.method == "POST":
            respostas = {}
            for item in execucao.sudo().modelo_id.item_ids:
                chave = "item_%s" % item.id
                arquivo = request.httprequest.files.get(chave + "_foto")
                respostas[str(item.id)] = {
                    "valor_bool": {"sim": True, "nao": False}.get(kw.get(chave)),
                    "valor_num": kw.get(chave) if item.tipo == "numero" else None,
                    "valor_texto": kw.get(chave + "_obs") or (kw.get(chave) if item.tipo == "texto" else None),
                    "foto": base64.b64encode(arquivo.read()) if arquivo and arquivo.filename else False,
                }
            try:
                with request.env.cr.savepoint():
                    execucao.sudo().finalizar(respostas, kw.get("pin"), user=request.env.user)
                return request.redirect("/boteco/checklist?feito=%s" % execucao_id)
            except UserError as e:
                erro = e.args[0]
        return request.render("boteco_checklists.tela_fazer", {
            "titulo": execucao.sudo().name, "tema": "claro", "execucao": execucao.sudo(), "erro": erro, "valores": kw,
        })
