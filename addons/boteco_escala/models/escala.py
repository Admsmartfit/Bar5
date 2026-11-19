"""Escala de turnos pela previsão de movimento (Etapa 29)."""

import math
from collections import defaultdict
from datetime import datetime, time, timedelta
from urllib.parse import quote

import pytz

from odoo import _, api, fields, models
from odoo.exceptions import UserError

from odoo.addons.boteco_base.models.boteco_perfil import CODIGOS_PERFIL

SEMANAS_HISTORICO = 4
DIAS = ["Segunda", "Terça", "Quarta", "Quinta", "Sexta", "Sábado", "Domingo"]


def _hora(valor):
    horas = int(valor or 0)
    return time(min(horas, 23), int(round(((valor or 0) - horas) * 60)) % 60)


class ResCompany(models.Model):
    _inherit = "res.company"

    boteco_flag_escala_turnos = fields.Boolean("Escala de turnos pela previsão de movimento", default=True)
    boteco_flag_ponto_pin = fields.Boolean("Ponto (entrada/saída) pelo PIN", default=True)
    boteco_ponto_so_na_rede = fields.Boolean("Ponto só na rede do bar", default=True)
    boteco_meta_custo_pessoal_pct = fields.Float("Meta de custo de pessoal (% do faturamento)", default=25.0)
    boteco_limite_horas_semana = fields.Float("Limite de horas por semana", default=44.0)


class BotecoTurno(models.Model):
    _name = "boteco.turno"
    _description = "Turno de trabalho"
    _order = "hora_inicio"

    name = fields.Char("Turno", required=True)
    hora_inicio = fields.Float("Começa", required=True, default=17.0)
    hora_fim = fields.Float("Termina", required=True, default=1.0, help="Menor que o início = termina no dia seguinte.")
    active = fields.Boolean(default=True)

    def _contem(self, hora_local):
        self.ensure_one()
        h = hora_local.hour + hora_local.minute / 60.0
        if self.hora_fim > self.hora_inicio:
            return self.hora_inicio <= h < self.hora_fim
        return h >= self.hora_inicio or h < self.hora_fim

    def _horas(self):
        self.ensure_one()
        return (self.hora_fim - self.hora_inicio) % 24 or 24

    def _intervalo(self, dia, tz):
        """(início, fim) em UTC naive do turno no dia (o da noite termina no dia seguinte)."""
        self.ensure_one()
        inicio = tz.localize(datetime.combine(dia, _hora(self.hora_inicio)))
        fim = inicio + timedelta(hours=self._horas())
        return inicio.astimezone(pytz.utc).replace(tzinfo=None), fim.astimezone(pytz.utc).replace(tzinfo=None)


class BotecoEscalaRegra(models.Model):
    _name = "boteco.escala.regra"
    _description = "Regra de cobertura por perfil"
    _order = "perfil"

    perfil = fields.Selection(CODIGOS_PERFIL, required=True)
    clientes_por_pessoa = fields.Integer("Clientes por pessoa", default=25,
                                         help="Ex.: 1 garçom a cada 25 clientes; 1 chapeiro a cada 50.")
    minimo = fields.Integer("Mínimo por turno", default=1)
    custo_hora = fields.Float("Custo por hora (R$)", default=15.0, help="Salário + encargos dividido pelas horas.")

    _sql_constraints = [("perfil_unico", "unique(perfil)", "Já existe regra para esse perfil.")]

    def _sugerir(self, clientes):
        self.ensure_one()
        return max(self.minimo, math.ceil(clientes / self.clientes_por_pessoa)) if self.clientes_por_pessoa else self.minimo


class BotecoEscalaSemana(models.Model):
    _name = "boteco.escala.semana"
    _description = "Escala da semana"
    _order = "inicio desc"

    name = fields.Char(compute="_compute_name", store=True)
    inicio = fields.Date("Semana de (segunda)", required=True,
                         default=lambda s: fields.Date.context_today(s) + timedelta(days=7 - fields.Date.context_today(s).weekday()))
    estado = fields.Selection([("rascunho", "Montando"), ("publicada", "Publicada")], default="rascunho", required=True)
    ajuste_ids = fields.One2many("boteco.escala.ajuste", "semana_id", string="Ajustes de movimento")
    previsao_ids = fields.One2many("boteco.escala.previsao", "semana_id", string="Previsão e sugestão")
    turno_ids = fields.One2many("boteco.escala.turno", "semana_id", string="Escala")
    faturamento_previsto = fields.Monetary("Faturamento previsto", compute="_compute_custos", currency_field="currency_id")
    custo_previsto = fields.Monetary("Custo de pessoal", compute="_compute_custos", currency_field="currency_id")
    custo_pct = fields.Float("% do faturamento", compute="_compute_custos")
    alertas = fields.Text(compute="_compute_alertas")
    currency_id = fields.Many2one(related="company_id.currency_id")
    company_id = fields.Many2one("res.company", required=True, default=lambda s: s.env.company)

    _sql_constraints = [("semana_unica", "unique(inicio, company_id)", "Já existe escala para essa semana.")]

    @api.depends("inicio")
    def _compute_name(self):
        for s in self:
            s.name = _("Semana de %s", s.inicio.strftime("%d/%m")) if s.inicio else _("Nova escala")

    @api.depends("previsao_ids.faturamento", "turno_ids.custo")
    def _compute_custos(self):
        for s in self:
            s.faturamento_previsto = sum(s.previsao_ids.mapped("faturamento"))
            s.custo_previsto = sum(s.turno_ids.mapped("custo"))
            s.custo_pct = round(s.custo_previsto * 100.0 / s.faturamento_previsto, 1) if s.faturamento_previsto else 0.0

    @api.constrains("inicio")
    def _check_segunda(self):
        for s in self:
            if s.inicio.weekday() != 0:
                raise UserError(_("A semana começa na segunda-feira."))

    def _dias(self):
        self.ensure_one()
        return [self.inicio + timedelta(days=i) for i in range(7)]

    # ------------------------------------------------------------------ previsão
    @api.model
    def _historico(self, company, ate):
        """Média de clientes e faturamento por (dia da semana, turno) nas últimas 4 semanas."""
        tz = company._boteco_tz()
        turnos = self.env["boteco.turno"].search([])
        de = ate - timedelta(days=7 * SEMANAS_HISTORICO)
        pedidos = self.env["pos.order"].sudo().search([
            ("company_id", "=", company.id), ("boteco_dia_operacao", ">=", de), ("boteco_dia_operacao", "<", ate),
            ("state", "in", ("paid", "done", "invoiced")),
        ])
        soma = defaultdict(lambda: [0.0, 0.0])
        for p in pedidos:
            local = pytz.utc.localize(p.date_order).astimezone(tz)
            for turno in turnos:
                if turno._contem(local):
                    chave = (p.boteco_dia_operacao.weekday(), turno.id)
                    soma[chave][0] += p.customer_count or 1
                    soma[chave][1] += p.amount_total
        return {k: (v[0] / SEMANAS_HISTORICO, v[1] / SEMANAS_HISTORICO) for k, v in soma.items()}

    def action_calcular(self):
        """Previsão por dia e turno (histórico + ajuste do dia) e quantas pessoas de cada perfil."""
        for s in self:
            if not s.company_id.boteco_recurso_ativo("escala_turnos"):
                raise UserError(_("A escala de turnos está desligada na Central de Recursos."))
            historico = self._historico(s.company_id, s.inicio)
            ajustes = {a.dia: a for a in s.ajuste_ids}
            regras = self.env["boteco.escala.regra"].search([])
            linhas = [fields.Command.clear()]
            for dia in s._dias():
                fator = 1 + (ajustes[dia].ajuste_pct / 100.0 if dia in ajustes else 0.0)
                for turno in self.env["boteco.turno"].search([]):
                    clientes, faturamento = historico.get((dia.weekday(), turno.id), (0.0, 0.0))
                    clientes, faturamento = round(clientes * fator), round(faturamento * fator, 2)
                    sugestao = {r.perfil: r._sugerir(clientes) for r in regras}
                    linhas.append(fields.Command.create({
                        "dia": dia, "turno_id": turno.id, "clientes": clientes, "faturamento": faturamento,
                        "sugestao": ", ".join("%s %s" % (n, dict(CODIGOS_PERFIL)[p].split(" ")[0].lower())
                                              for p, n in sorted(sugestao.items())),
                        "sugestao_json": str(sugestao),
                    }))
            s.previsao_ids = linhas
        return True

    # ------------------------------------------------------------------ conferência e publicação
    def _problemas(self):
        self.ensure_one()
        problemas = []
        limite = self.company_id.boteco_limite_horas_semana or 44.0
        for user in self.turno_ids.user_id:
            dele = self.turno_ids.filtered(lambda t, u=user: t.user_id == u)
            horas = sum(dele.mapped("horas"))
            if horas > limite:
                problemas.append(_("%(n)s: %(h)s h na semana (limite %(l)s h).", n=user.name, h=round(horas, 1), l=limite))
            if len(set(dele.mapped("dia"))) >= 7:
                problemas.append(_("%s: sem folga na semana.", user.name))
        for prev in self.previsao_ids:
            sugestao = prev._sugestao()
            escalados = self.turno_ids.filtered(lambda t, p=prev: t.dia == p.dia and t.turno_id == p.turno_id)
            for perfil, quantos in sugestao.items():
                tem = len(escalados.filtered(lambda t, pf=perfil: t.perfil == pf))
                if prev.clientes and tem < quantos:
                    problemas.append(_("%(d)s %(dd)s, %(t)s: %(tem)s de %(q)s %(p)s (turno descoberto).",
                                       d=DIAS[prev.dia.weekday()], dd=prev.dia.strftime("%d/%m"), t=prev.turno_id.name,
                                       tem=tem, q=quantos, p=dict(CODIGOS_PERFIL)[perfil]))
        return problemas

    @api.depends("turno_ids", "turno_ids.horas", "previsao_ids")
    def _compute_alertas(self):
        for s in self:
            s.alertas = "\n".join(s._problemas()) if s.inicio else False

    def action_publicar(self):
        self.ensure_one()
        problemas = self._problemas()
        if problemas and not self.env.context.get("boteco_confirmado"):
            confirmar = self.env["boteco.escala.confirmar"].create({"semana_id": self.id, "alertas": "\n".join(problemas)})
            return {"type": "ir.actions.act_window", "res_model": "boteco.escala.confirmar", "res_id": confirmar.id,
                    "view_mode": "form", "target": "new", "name": _("Publicar com alertas?")}
        self.estado = "publicada"
        return True

    def action_reabrir(self):
        self.write({"estado": "rascunho"})


class BotecoEscalaAjuste(models.Model):
    _name = "boteco.escala.ajuste"
    _description = "Ajuste de movimento de um dia (feriado, jogo, show)"

    semana_id = fields.Many2one("boteco.escala.semana", required=True, ondelete="cascade")
    dia = fields.Date(required=True)
    ajuste_pct = fields.Float("Ajuste (%)", help="+30 = 30% mais movimento (jogo, show); -50 = feriado fraco.")
    motivo = fields.Char()


class BotecoEscalaPrevisao(models.Model):
    _name = "boteco.escala.previsao"
    _description = "Previsão de movimento por turno"
    _order = "dia, turno_id"

    semana_id = fields.Many2one("boteco.escala.semana", required=True, ondelete="cascade")
    dia = fields.Date(required=True)
    dia_semana = fields.Char(compute="_compute_dia_semana")
    turno_id = fields.Many2one("boteco.turno", required=True)
    clientes = fields.Integer("Clientes previstos")
    faturamento = fields.Float("Faturamento previsto", digits=(16, 2))
    sugestao = fields.Char("Sugestão de equipe")
    sugestao_json = fields.Char()
    escalados = fields.Char("Escalados", compute="_compute_escalados")

    def _compute_dia_semana(self):
        for p in self:
            p.dia_semana = DIAS[p.dia.weekday()] if p.dia else ""

    def _sugestao(self):
        import ast
        try:
            return ast.literal_eval(self.sugestao_json or "{}")
        except (ValueError, SyntaxError):
            return {}

    def _compute_escalados(self):
        for p in self:
            turnos = p.semana_id.turno_ids.filtered(lambda t: t.dia == p.dia and t.turno_id == p.turno_id)
            contagem = defaultdict(int)
            for t in turnos:
                contagem[t.perfil] += 1
            p.escalados = ", ".join("%s %s" % (n, dict(CODIGOS_PERFIL).get(pf, pf or "?").split(" ")[0].lower())
                                    for pf, n in sorted(contagem.items(), key=lambda x: x[0] or "")) or "—"


class BotecoEscalaTurno(models.Model):
    _name = "boteco.escala.turno"
    _description = "Turno escalado"
    _order = "inicio, user_id"

    semana_id = fields.Many2one("boteco.escala.semana", required=True, ondelete="cascade", index=True)
    user_id = fields.Many2one("res.users", string="Pessoa", required=True, index=True,
                              domain=[("share", "=", False), ("boteco_perfil_id", "!=", False)])
    perfil = fields.Selection(CODIGOS_PERFIL, compute="_compute_perfil", store=True, readonly=False)
    dia = fields.Date(required=True)
    turno_id = fields.Many2one("boteco.turno", required=True)
    inicio = fields.Datetime(compute="_compute_horario", store=True, readonly=False)
    fim = fields.Datetime(compute="_compute_horario", store=True, readonly=False)
    horas = fields.Float(compute="_compute_horas", store=True)
    custo = fields.Float(compute="_compute_horas", store=True, digits=(16, 2))
    estado_semana = fields.Selection(related="semana_id.estado", store=True)

    @api.depends("user_id")
    def _compute_perfil(self):
        for t in self:
            t.perfil = t.user_id.boteco_perfil_id.codigo or t.perfil

    @api.depends("dia", "turno_id")
    def _compute_horario(self):
        for t in self:
            if t.dia and t.turno_id:
                t.inicio, t.fim = t.turno_id._intervalo(t.dia, t.semana_id.company_id._boteco_tz())

    @api.depends("inicio", "fim", "perfil")
    def _compute_horas(self):
        regras = {r.perfil: r for r in self.env["boteco.escala.regra"].search([])}
        for t in self:
            t.horas = (t.fim - t.inicio).total_seconds() / 3600.0 if t.inicio and t.fim else 0.0
            t.custo = round(t.horas * (regras[t.perfil].custo_hora if t.perfil in regras else 0.0), 2)

    def write(self, vals):
        # Arrastar no calendário muda o dia: o turno acompanha
        if "inicio" in vals and "dia" not in vals and len(self) == 1:
            tz = self.semana_id.company_id._boteco_tz()
            vals["dia"] = pytz.utc.localize(fields.Datetime.to_datetime(vals["inicio"])).astimezone(tz).date()
        return super().write(vals)

    def action_whatsapp(self):
        """Manda para a pessoa a escala dela na semana (link pronto do WhatsApp)."""
        self.ensure_one()
        from odoo.addons.boteco_pos.models.boteco_crm import link_whatsapp
        dele = self.semana_id.turno_ids.filtered(lambda t: t.user_id == self.user_id).sorted("inicio")
        tz = self.semana_id.company_id._boteco_tz()
        linhas = ["• %s %s: %s às %s" % (DIAS[t.dia.weekday()], t.dia.strftime("%d/%m"), *(
            pytz.utc.localize(x).astimezone(tz).strftime("%H:%M") for x in (t.inicio, t.fim))) for t in dele]
        mensagem = _("Olá, %(n)s! Sua escala da %(s)s:\n%(l)s", n=(self.user_id.name or "").split(" ")[0],
                     s=self.semana_id.name.lower(), l="\n".join(linhas))
        telefone = self.user_id.partner_id.mobile or self.user_id.partner_id.phone
        url = link_whatsapp(telefone, mensagem) if telefone else "https://wa.me/?text=%s" % quote(mensagem)
        return {"type": "ir.actions.act_url", "url": url, "target": "new"}


class BotecoEscalaConfirmar(models.TransientModel):
    _name = "boteco.escala.confirmar"
    _description = "Confirmar publicação com alertas"

    semana_id = fields.Many2one("boteco.escala.semana", required=True)
    alertas = fields.Text(readonly=True)

    def action_confirmar(self):
        return self.semana_id.with_context(boteco_confirmado=True).action_publicar()


class BotecoEscalaTroca(models.Model):
    _name = "boteco.escala.troca"
    _description = "Pedido de troca de turno"
    _order = "create_date desc"

    turno_id = fields.Many2one("boteco.escala.turno", string="Meu turno", required=True, ondelete="cascade",
                               domain="[('user_id', '=', uid), ('estado_semana', '=', 'publicada')]")
    pedido_por_id = fields.Many2one("res.users", default=lambda s: s.env.user, readonly=True)
    para_user_id = fields.Many2one("res.users", string="Quem assume", required=True,
                                   domain=[("share", "=", False), ("boteco_perfil_id", "!=", False)])
    motivo = fields.Char()
    estado = fields.Selection([("pedida", "Esperando o gerente"), ("aprovada", "Aprovada"), ("recusada", "Recusada")],
                              default="pedida", required=True)

    @api.constrains("turno_id", "pedido_por_id")
    def _check_dono_do_turno(self):
        for troca in self:
            if troca.turno_id.user_id != troca.pedido_por_id and not self.env.su:
                raise UserError(_("Só dá para pedir troca do próprio turno."))

    def action_aprovar(self):
        if not self.env.user.has_group("boteco_base.group_gerente"):
            raise UserError(_("Só o gerente aprova a troca."))
        for troca in self.filtered(lambda t: t.estado == "pedida"):
            troca.turno_id.sudo().user_id = troca.para_user_id  # a troca só vale aqui
            troca.estado = "aprovada"
        return True

    def action_recusar(self):
        if not self.env.user.has_group("boteco_base.group_gerente"):
            raise UserError(_("Só o gerente recusa a troca."))
        self.write({"estado": "recusada"})
