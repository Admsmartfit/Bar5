"""Checklists de abertura/fechamento e APPCC (RDC 216) com foto e assinatura por PIN (Etapa 30)."""

from datetime import datetime, time, timedelta

import pytz

from odoo import _, api, fields, models
from odoo.exceptions import UserError

FREQUENCIAS = [("abertura", "Na abertura"), ("fechamento", "No fechamento"), ("diaria", "Todo dia"),
               ("semanal", "Toda semana")]
TIPOS_ITEM = [("simnao", "Sim / Não"), ("numero", "Número (faixa)"), ("foto", "Foto"), ("texto", "Texto")]
DIAS = [("0", "Segunda"), ("1", "Terça"), ("2", "Quarta"), ("3", "Quinta"), ("4", "Sexta"), ("5", "Sábado"),
        ("6", "Domingo")]


def _tz(company):
    return pytz.timezone(company.partner_id.tz or "America/Sao_Paulo")


class BotecoChecklistModelo(models.Model):
    _name = "boteco.checklist.modelo"
    _description = "Modelo de checklist"
    _order = "sequence, name"

    name = fields.Char("Checklist", required=True)
    sequence = fields.Integer(default=10)
    frequencia = fields.Selection(FREQUENCIAS, required=True, default="abertura")
    dia_semana = fields.Selection(DIAS, string="Dia (semanal)", default="0")
    hora_limite = fields.Float("Fazer até (hora)", default=18.0, help="Depois disso fica vermelho para o gerente.")
    grupo_id = fields.Many2one("res.groups", string="Quem faz", domain=[("category_id.name", "ilike", "boteco")],
                               help="Perfil responsável: as pendências aparecem para quem tem esse perfil.")
    setor = fields.Char("Setor", help="Salão, cozinha, bar, estoque…")
    item_ids = fields.One2many("boteco.checklist.item", "modelo_id", string="Itens", copy=True)
    codigo_padrao = fields.Char(readonly=True, copy=False)
    active = fields.Boolean(default=True)
    company_id = fields.Many2one("res.company", required=True, default=lambda s: s.env.company)

    def _vale_hoje(self, dia):
        self.ensure_one()
        return self.frequencia != "semanal" or str(dia.weekday()) == (self.dia_semana or "0")

    def action_usar(self):
        self.write({"active": True})
        self.env["boteco.checklist.execucao"]._cron_gerar()
        return True


class BotecoChecklistItem(models.Model):
    _name = "boteco.checklist.item"
    _description = "Item de checklist"
    _order = "sequence, id"

    modelo_id = fields.Many2one("boteco.checklist.modelo", required=True, ondelete="cascade")
    sequence = fields.Integer(default=10)
    name = fields.Char("O que conferir", required=True)
    tipo = fields.Selection(TIPOS_ITEM, required=True, default="simnao")
    minimo = fields.Float("Mínimo aceito")
    maximo = fields.Float("Máximo aceito")
    unidade = fields.Char(default="°C")
    critico = fields.Boolean("Crítico", help="Se não estiver conforme, o gerente é avisado na hora e abre não conformidade.")
    foto_obrigatoria = fields.Boolean("Foto obrigatória")


class BotecoChecklistExecucao(models.Model):
    _name = "boteco.checklist.execucao"
    _description = "Checklist do dia"
    _order = "data desc, hora_limite, id"

    modelo_id = fields.Many2one("boteco.checklist.modelo", required=True, ondelete="restrict", index=True)
    name = fields.Char(related="modelo_id.name", store=True)
    data = fields.Date(required=True, index=True)
    hora_limite = fields.Datetime("Fazer até")
    grupo_id = fields.Many2one(related="modelo_id.grupo_id", store=True)
    estado = fields.Selection([("pendente", "Pendente"), ("feito", "Feito")], default="pendente", required=True, index=True)
    atrasado = fields.Boolean(compute="_compute_atrasado", search="_search_atrasado")
    resposta_ids = fields.One2many("boteco.checklist.resposta", "execucao_id", string="Respostas")
    assinado_por_id = fields.Many2one("res.users", string="Assinado por (PIN)", readonly=True)
    assinado_em = fields.Datetime(readonly=True)
    n_nao_conformes = fields.Integer("Fora do padrão", compute="_compute_n_nc", store=True)
    company_id = fields.Many2one("res.company", required=True, default=lambda s: s.env.company, index=True)

    _sql_constraints = [("um_por_dia", "unique(modelo_id, data)", "Esse checklist já existe para o dia.")]

    def _compute_atrasado(self):
        agora = fields.Datetime.now()
        for e in self:
            e.atrasado = e.estado == "pendente" and bool(e.hora_limite) and e.hora_limite < agora

    def _search_atrasado(self, operador, valor):
        positivo = (operador == "=" and valor) or (operador == "!=" and not valor)
        dominio = [("estado", "=", "pendente"), ("hora_limite", "<", fields.Datetime.now())]
        return dominio if positivo else ["!", "&"] + dominio

    @api.depends("resposta_ids.conforme")
    def _compute_n_nc(self):
        for e in self:
            e.n_nao_conformes = len(e.resposta_ids.filtered(lambda r: not r.conforme))

    @api.model
    def _cron_gerar(self):
        """Todo dia cedo: cria os checklists do dia (e as pendências de quem faz)."""
        for company in self.env["res.company"].search([]):
            if not company.boteco_recurso_ativo("checklists_appcc"):
                continue
            tz = _tz(company)
            hoje = datetime.now(tz).date()
            for modelo in self.env["boteco.checklist.modelo"].search([("company_id", "=", company.id)]):
                if not modelo._vale_hoje(hoje) or self.search_count([("modelo_id", "=", modelo.id), ("data", "=", hoje)]):
                    continue
                horas = int(modelo.hora_limite or 0)
                minutos = int(round(((modelo.hora_limite or 0) - horas) * 60))
                limite = tz.localize(datetime.combine(hoje, time(min(horas, 23), min(minutos, 59))))
                self.sudo().create({"modelo_id": modelo.id, "data": hoje, "company_id": company.id,
                                    "hora_limite": limite.astimezone(pytz.utc).replace(tzinfo=None)})
        return True

    @api.model
    def pendentes_para(self, user=None):
        """Checklists de hoje que esse usuário pode fazer (pelo perfil)."""
        user = user or self.env.user
        hoje = datetime.now(_tz(user.company_id)).date()
        execucoes = self.sudo().search([("data", "=", hoje), ("estado", "=", "pendente"),
                                        ("company_id", "=", user.company_id.id)])
        return execucoes.filtered(lambda e: not e.grupo_id or e.grupo_id in user.groups_id
                                  or user.has_group("boteco_base.group_gerente"))

    def finalizar(self, respostas, pin, user=None):
        """respostas: {item_id: {"valor_bool", "valor_num", "valor_texto", "foto"}}; assina com o PIN de quem fez."""
        self.ensure_one()
        if self.estado == "feito":
            raise UserError(_("Esse checklist já foi assinado."))
        quem = user or self.env.user
        if not quem._boteco_pin_confere(pin):
            raise UserError(_("PIN não confere."))
        Resposta = self.env["boteco.checklist.resposta"].sudo()
        faltando = []
        for item in self.modelo_id.item_ids:
            dado = respostas.get(str(item.id)) or respostas.get(item.id) or {}
            vals = {"execucao_id": self.id, "item_id": item.id,
                    "valor_bool": dado.get("valor_bool") in (True, "1", "sim", "true", 1),
                    "valor_texto": (dado.get("valor_texto") or "").strip()[:500] or False,
                    "foto": dado.get("foto") or False}
            if item.tipo == "numero":
                try:
                    vals["valor_num"] = float(str(dado.get("valor_num")).replace(",", "."))
                except (TypeError, ValueError):
                    faltando.append(item.name)
                    continue
            if item.tipo == "simnao" and dado.get("valor_bool") is None:
                faltando.append(item.name)
            if (item.foto_obrigatoria or item.tipo == "foto") and not vals["foto"]:
                faltando.append(_("%s (foto)", item.name))
            if item.tipo == "texto" and not vals["valor_texto"]:
                faltando.append(item.name)
            Resposta.create(vals)
        if faltando:
            raise UserError(_("Falta responder: %s", ", ".join(faltando)))
        self.sudo().write({"estado": "feito", "assinado_por_id": quem.id, "assinado_em": fields.Datetime.now()})
        for resposta in self.resposta_ids.filtered(lambda r: not r.conforme):
            resposta._abrir_nao_conformidade()
        return True


class BotecoChecklistResposta(models.Model):
    _name = "boteco.checklist.resposta"
    _description = "Resposta de checklist"
    _order = "id"

    execucao_id = fields.Many2one("boteco.checklist.execucao", required=True, ondelete="cascade", index=True)
    item_id = fields.Many2one("boteco.checklist.item", required=True, ondelete="restrict")
    name = fields.Char(related="item_id.name")
    tipo = fields.Selection(related="item_id.tipo")
    critico = fields.Boolean(related="item_id.critico")
    valor_bool = fields.Boolean("Sim")
    valor_num = fields.Float("Valor")
    valor_texto = fields.Char("Observação")
    foto = fields.Image("Foto", max_width=1280, max_height=1280, attachment=True)
    conforme = fields.Boolean(compute="_compute_conforme", store=True)

    @api.depends("valor_bool", "valor_num", "item_id.tipo", "item_id.minimo", "item_id.maximo")
    def _compute_conforme(self):
        for r in self:
            item = r.item_id
            if item.tipo == "simnao":
                r.conforme = r.valor_bool
            elif item.tipo == "numero":
                r.conforme = (item.minimo == item.maximo == 0) or item.minimo <= r.valor_num <= item.maximo
            else:
                r.conforme = True

    def _abrir_nao_conformidade(self):
        """Fora do padrão: tarefa com prazo. Item crítico avisa o gerente na hora."""
        self.ensure_one()
        item = self.item_id
        descricao = item.name
        if item.tipo == "numero":
            descricao = _("%(n)s: %(v)s %(u)s (aceito de %(a)s a %(b)s)", n=item.name, v=self.valor_num,
                          u=item.unidade or "", a=item.minimo, b=item.maximo)
        nc = self.env["boteco.nao.conformidade"].sudo().create({
            "resposta_id": self.id, "descricao": descricao, "critica": item.critico,
            "prazo": fields.Date.context_today(self) + timedelta(days=0 if item.critico else 2),
            "company_id": self.execucao_id.company_id.id,
        })
        if item.critico:
            nc._avisar_gerentes()
        return nc


class BotecoNaoConformidade(models.Model):
    _name = "boteco.nao.conformidade"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _description = "Não conformidade (APPCC)"
    _order = "estado, prazo, id desc"

    name = fields.Char(compute="_compute_name", store=True)
    resposta_id = fields.Many2one("boteco.checklist.resposta", ondelete="set null")
    execucao_id = fields.Many2one(related="resposta_id.execucao_id", store=True)
    descricao = fields.Char("O que estava errado", required=True)
    critica = fields.Boolean("Crítica")
    responsavel_id = fields.Many2one("res.users", string="Responsável")
    prazo = fields.Date(required=True, default=fields.Date.context_today)
    acao = fields.Text("O que foi feito")
    estado = fields.Selection([("aberta", "Aberta"), ("resolvida", "Resolvida")], default="aberta", required=True, index=True)
    resolvida_em = fields.Datetime(readonly=True)
    company_id = fields.Many2one("res.company", required=True, default=lambda s: s.env.company)

    @api.depends("descricao", "execucao_id.name")
    def _compute_name(self):
        for nc in self:
            nc.name = "%s – %s" % (nc.execucao_id.name or _("APPCC"), nc.descricao or "")

    def action_resolver(self):
        for nc in self:
            if not (nc.acao or "").strip():
                raise UserError(_("Escreva o que foi feito para resolver."))
        self.write({"estado": "resolvida", "resolvida_em": fields.Datetime.now()})
        self.env["mail.activity"].sudo().search([("res_model", "=", self._name), ("res_id", "in", self.ids)]).unlink()
        return True

    def _gerentes(self):
        return self.env.ref("boteco_base.group_gerente").sudo().users.filtered(lambda u: u.active and not u.share)

    def _avisar_gerentes(self):
        """Aviso na hora (notificação na tela de quem está conectado) e pendência para cada gerente."""
        tipo = self.env.ref("mail.mail_activity_data_todo", raise_if_not_found=False)
        for nc in self:
            for gerente in nc._gerentes()[:10]:
                gerente.partner_id._bus_send("simple_notification", {
                    "title": _("Item crítico fora do padrão"), "message": nc.name, "type": "danger", "sticky": True})
                if tipo:
                    nc.sudo().activity_schedule(activity_type_id=tipo.id, user_id=gerente.id, date_deadline=nc.prazo,
                                                summary=_("Resolver: %s", nc.descricao)[:100])

    @api.model
    def _cron_lembrar(self):
        """Não conformidade vencida reaparece todo dia até ser resolvida."""
        hoje = fields.Date.context_today(self)
        vencidas = self.sudo().search([("estado", "=", "aberta"), ("prazo", "<", hoje)])
        tipo = self.env.ref("mail.mail_activity_data_todo", raise_if_not_found=False)
        for nc in vencidas:
            if not tipo or self.env["mail.activity"].sudo().search_count(
                    [("res_model", "=", self._name), ("res_id", "=", nc.id), ("date_deadline", ">=", hoje)]):
                continue
            for gerente in nc._gerentes()[:10]:
                nc.activity_schedule(activity_type_id=tipo.id, user_id=gerente.id, date_deadline=hoje,
                                     summary=_("Ainda aberta: %s", nc.descricao)[:100])
        return True
