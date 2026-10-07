from datetime import datetime, time, timedelta

import pytz

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

DIAS = [
    ("seg", "Segunda"),
    ("ter", "Terça"),
    ("qua", "Quarta"),
    ("qui", "Quinta"),
    ("sex", "Sexta"),
    ("sab", "Sábado"),
    ("dom", "Domingo"),
]


def hora_para_time(valor):
    """17.5 -> 17:30. 24.0 -> 23:59:59 (fim do dia)."""
    if valor >= 24:
        return time(23, 59, 59)
    horas = int(valor)
    minutos = int(round((valor - horas) * 60))
    if minutos == 60:
        horas, minutos = horas + 1, 0
    return time(horas, minutos)


class BotecoHappyHour(models.Model):
    """Horário de happy hour. Os preços ficam no produto (campo "Preço happy hour")."""

    _name = "boteco.happy.hour"
    _description = "Happy hour"
    _order = "sequence, id"

    name = fields.Char("Nome", required=True, default="Happy hour")
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    company_id = fields.Many2one("res.company", default=lambda s: s.env.company, required=True)
    hora_inicio = fields.Float("Começa às", default=17.0, required=True)
    hora_fim = fields.Float("Termina às", default=21.0, required=True,
                            help="Se for menor que o início, termina no dia seguinte (ex.: 22h às 1h).")
    seg = fields.Boolean("Seg")
    ter = fields.Boolean("Ter")
    qua = fields.Boolean("Qua", default=True)
    qui = fields.Boolean("Qui", default=True)
    sex = fields.Boolean("Sex", default=True)
    sab = fields.Boolean("Sáb", default=True)
    dom = fields.Boolean("Dom", default=True)
    resumo = fields.Char(compute="_compute_resumo", string="Quando")

    @api.depends("hora_inicio", "hora_fim", *[d for d, _n in DIAS])
    def _compute_resumo(self):
        for hh in self:
            dias = [nome[:3] for codigo, nome in DIAS if hh[codigo]]
            hh.resumo = "%s, %s às %s" % (
                ", ".join(dias) or _("nenhum dia"),
                hora_para_time(hh.hora_inicio).strftime("%Hh%M").replace("h00", "h"),
                hora_para_time(hh.hora_fim).strftime("%Hh%M").replace("h00", "h"),
            )

    @api.constrains("hora_inicio", "hora_fim")
    def _check_horas(self):
        for hh in self:
            if not (0 <= hh.hora_inicio < 24) or not (0 < hh.hora_fim <= 24):
                raise ValidationError(_("Horário inválido no happy hour."))
            if hh.hora_inicio == hh.hora_fim:
                raise ValidationError(_("O happy hour precisa começar e terminar em horários diferentes."))

    # ------------------------------------------------------------------
    def _janelas(self, dia):
        """Janelas (inicio, fim) locais que COMEÇAM no dia (date)."""
        janelas = []
        for hh in self:
            if not hh[DIAS[dia.weekday()][0]]:
                continue
            inicio = datetime.combine(dia, hora_para_time(hh.hora_inicio))
            fim = datetime.combine(dia, hora_para_time(hh.hora_fim))
            if hh.hora_fim >= 24:
                fim = datetime.combine(dia + timedelta(days=1), time.min)
            elif fim <= inicio:
                fim += timedelta(days=1)
            janelas.append((inicio, fim))
        return janelas

    @api.model
    def _agora_local(self, momento=None, company=None):
        """Momento (UTC naive) convertido para o fuso da empresa, sem tz (naive local)."""
        company = company or self.env.company
        momento = momento or fields.Datetime.now()
        tz = company._boteco_tz()
        return pytz.utc.localize(momento).astimezone(tz).replace(tzinfo=None), tz

    @api.model
    def _ativos(self, company=None):
        company = company or self.env.company
        return self.search([("company_id", "=", company.id)])

    @api.model
    def _ativo_em(self, momento=None, company=None):
        local, _tz = self._agora_local(momento, company)
        for dia in (local.date() - timedelta(days=1), local.date()):
            for inicio, fim in self._ativos(company)._janelas(dia):
                if inicio <= local < fim:
                    return True
        return False

    @api.model
    def _proxima_troca(self, momento=None, company=None):
        """Próximo instante (UTC naive) em que o happy hour liga ou desliga. None se nunca."""
        company = company or self.env.company
        local, tz = self._agora_local(momento, company)
        registros = self._ativos(company)
        if not registros:
            return None
        estado_atual = self._ativo_em(momento, company)
        candidatos = set()
        for i in range(-1, 9):
            for inicio, fim in registros._janelas(local.date() + timedelta(days=i)):
                candidatos.update(t for t in (inicio, fim) if t > local)
        for candidato in sorted(candidatos):
            utc = tz.localize(candidato).astimezone(pytz.utc).replace(tzinfo=None)
            if self._ativo_em(utc, company) != estado_atual:
                return utc
        return None

    def write(self, vals):
        res = super().write(vals)
        self.env["pos.config"]._boteco_avisar_cardapio()
        return res

    @api.model_create_multi
    def create(self, vals_list):
        res = super().create(vals_list)
        self.env["pos.config"]._boteco_avisar_cardapio()
        return res
