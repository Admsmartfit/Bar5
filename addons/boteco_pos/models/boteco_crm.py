"""Régua de relacionamento (Etapa 22): clientes que sumiram e aniversariantes, com mensagem pronta.

O envio é pelo link do WhatsApp (wa.me), aberto por quem está operando: não depende de nenhum robô.
"""

import re
from datetime import timedelta
from urllib.parse import quote

from odoo import _, fields, models
from odoo.exceptions import UserError

PAGOS = ("paid", "done", "invoiced")


def link_whatsapp(telefone, mensagem):
    numero = re.sub(r"\D", "", telefone or "")
    if numero and not numero.startswith("55"):
        numero = "55" + numero
    return "https://wa.me/%s?text=%s" % (numero, quote(mensagem)) if numero else ""


class BotecoReguaCrm(models.TransientModel):
    _name = "boteco.regua.crm"
    _description = "Clientes sumidos e aniversariantes"

    dias_sumido = fields.Integer("Sumido há mais de (dias)", default=21, required=True)
    dias_aniversario = fields.Integer("Aniversário nos próximos (dias)", default=7, required=True)
    linha_ids = fields.One2many("boteco.regua.crm.linha", "regua_id", string="Clientes")

    def action_gerar(self):
        self.ensure_one()
        company = self.env.company
        if not company.boteco_recurso_ativo("crm_whatsapp_ia"):
            raise UserError(_("A régua de clientes está desligada na Central de Recursos."))
        hoje = fields.Date.context_today(self)
        self.env.cr.execute(
            """
            SELECT partner_id, MAX(date_order), COUNT(*), SUM(amount_total)
              FROM pos_order
             WHERE partner_id IS NOT NULL AND company_id = %s AND state IN %s
             GROUP BY partner_id
            """,
            (company.id, PAGOS),
        )
        historico = {pid: (ultima, visitas, total) for pid, ultima, visitas, total in self.env.cr.fetchall()}
        Parceiro = self.env["res.partner"]
        linhas = [fields.Command.clear()]
        limite = hoje - timedelta(days=self.dias_sumido)
        for pid, (ultima, visitas, total) in historico.items():
            if ultima.date() <= limite:
                cliente = Parceiro.browse(pid)
                nome = (cliente.name or "").split(" ")[0]
                mensagem = _("Oi, %(n)s! Faz tempo que você não aparece no %(bar)s. Bora um chope esta semana? 🍺",
                             n=nome, bar=company.name)
                linhas.append(fields.Command.create({
                    "partner_id": pid, "motivo": "sumido", "ultima_visita": ultima.date(),
                    "dias": (hoje - ultima.date()).days, "visitas": visitas, "total_gasto": total or 0.0,
                    "mensagem": mensagem, "link_whatsapp": link_whatsapp(cliente.mobile or cliente.phone, mensagem),
                }))
        for cliente in Parceiro.search([("boteco_aniversario", "!=", False)]):
            aniversario = cliente.boteco_aniversario
            try:
                proximo = aniversario.replace(year=hoje.year)
            except ValueError:  # 29/02 em ano não bissexto
                proximo = aniversario.replace(year=hoje.year, day=28)
            if proximo < hoje:
                proximo = proximo.replace(year=hoje.year + 1)
            if (proximo - hoje).days > self.dias_aniversario:
                continue
            ultima, visitas, total = historico.get(cliente.id, (None, 0, 0.0))
            nome = (cliente.name or "").split(" ")[0]
            mensagem = _("Parabéns, %(n)s! 🎉 Comemore com a gente no %(bar)s: a primeira rodada é por nossa conta.",
                         n=nome, bar=company.name)
            linhas.append(fields.Command.create({
                "partner_id": cliente.id, "motivo": "aniversario", "aniversario": proximo,
                "ultima_visita": ultima.date() if ultima else False, "visitas": visitas, "total_gasto": total or 0.0,
                "mensagem": mensagem, "link_whatsapp": link_whatsapp(cliente.mobile or cliente.phone, mensagem),
            }))
        self.linha_ids = linhas
        return {"type": "ir.actions.act_window", "res_model": self._name, "res_id": self.id, "view_mode": "form",
                "target": "new"}


class BotecoReguaCrmLinha(models.TransientModel):
    _name = "boteco.regua.crm.linha"
    _description = "Cliente na régua"
    _order = "motivo, dias desc"

    regua_id = fields.Many2one("boteco.regua.crm", required=True, ondelete="cascade")
    partner_id = fields.Many2one("res.partner", string="Cliente")
    motivo = fields.Selection([("sumido", "Sumiu"), ("aniversario", "Aniversário")])
    ultima_visita = fields.Date("Última visita")
    dias = fields.Integer("Dias sem vir")
    aniversario = fields.Date("Aniversário")
    visitas = fields.Integer("Visitas")
    total_gasto = fields.Float("Total gasto", digits=(16, 2))
    mensagem = fields.Text("Mensagem")
    link_whatsapp = fields.Char("WhatsApp")

    def action_abrir_whatsapp(self):
        self.ensure_one()
        if not self.link_whatsapp:
            raise UserError(_("Cliente sem telefone cadastrado."))
        return {"type": "ir.actions.act_url", "url": self.link_whatsapp, "target": "new"}
