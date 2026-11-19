"""Ponto pelo PIN (hr_attendance gratuito) e relatório escalado x trabalhado (Etapa 29)."""

import base64
import csv
import io
from datetime import datetime, time, timedelta

import pytz

from odoo import _, api, fields, models
from odoo.exceptions import UserError

TOLERANCIA_ATRASO_MIN = 5


class BotecoPonto(models.AbstractModel):
    _name = "boteco.ponto"
    _description = "Ponto pelo PIN"

    @api.model
    def _funcionario(self, user):
        funcionario = self.env["hr.employee"].sudo().search([("user_id", "=", user.id)], limit=1)
        if not funcionario:
            funcionario = self.env["hr.employee"].sudo().create({"name": user.name, "user_id": user.id,
                                                                 "company_id": user.company_id.id})
        return funcionario

    @api.model
    def bater(self, user, pin, ip=None, na_rede=True):
        """Entrada ou saída (alterna). Devolve {"tipo": "entrada"|"saida", "hora": "HH:MM", "nome"}."""
        company = user.company_id
        if not company.boteco_recurso_ativo("ponto_pin"):
            raise UserError(_("O ponto pelo PIN está desligado."))
        if company.boteco_ponto_so_na_rede and not na_rede:
            raise UserError(_("Ponto só pela rede do bar. Conecte-se ao Wi-Fi do bar."))
        Tentativa = self.env["boteco.pin.tentativa"].sudo()
        if Tentativa._bloqueado(user.id, "ponto"):
            raise UserError(_("Muitos PINs errados. Espere 15 minutos ou fale com o gerente."))
        certo = user._boteco_pin_confere(pin)
        Tentativa._registrar_isolado(user.id, "ponto", certo, ip)
        if not certo:
            raise UserError(_("PIN não confere."))
        funcionario = self._funcionario(user)
        Presenca = self.env["hr.attendance"].sudo()
        aberta = Presenca.search([("employee_id", "=", funcionario.id), ("check_out", "=", False)], limit=1)
        agora = fields.Datetime.now()
        if aberta:
            aberta.check_out = agora
            tipo = "saida"
        else:
            Presenca.create({"employee_id": funcionario.id, "check_in": agora})
            tipo = "entrada"
        hora = pytz.utc.localize(agora).astimezone(company._boteco_tz()).strftime("%H:%M")
        return {"tipo": tipo, "hora": hora, "nome": user.name}


class BotecoEscalaRelatorio(models.TransientModel):
    _name = "boteco.escala.relatorio"
    _description = "Escalado x trabalhado"

    data_de = fields.Date("De", required=True, default=lambda s: fields.Date.context_today(s) - timedelta(days=7))
    data_ate = fields.Date("Até", required=True, default=fields.Date.context_today)
    linha_ids = fields.One2many("boteco.escala.relatorio.linha", "relatorio_id", string="Pessoas e dias")

    def action_gerar(self):
        self.ensure_one()
        company = self.env.company
        tz = company._boteco_tz()
        turnos = self.env["boteco.escala.turno"].sudo().search([
            ("dia", ">=", self.data_de), ("dia", "<=", self.data_ate), ("estado_semana", "=", "publicada"),
            ("semana_id.company_id", "=", company.id)], order="inicio")
        Presenca = self.env["hr.attendance"].sudo()
        local = lambda dt: pytz.utc.localize(dt).astimezone(tz) if dt else None  # noqa: E731
        linhas = [fields.Command.clear()]
        for t in turnos:
            funcionario = self.env["hr.employee"].sudo().search([("user_id", "=", t.user_id.id)], limit=1)
            presencas = Presenca.search([("employee_id", "=", funcionario.id),
                                         ("check_in", ">=", t.inicio - timedelta(hours=4)),
                                         ("check_in", "<=", t.fim)], order="check_in") if funcionario else Presenca
            entrada = presencas[:1].check_in
            saida = presencas[-1:].check_out if presencas else False
            trabalhadas = sum(((p.check_out or p.check_in) - p.check_in).total_seconds() for p in presencas) / 3600.0
            atraso = max(0, int((entrada - t.inicio).total_seconds() // 60)) if entrada else 0
            linhas.append(fields.Command.create({
                "user_id": t.user_id.id, "dia": t.dia, "turno": t.turno_id.name,
                "escalado": "%s–%s" % (local(t.inicio).strftime("%H:%M"), local(t.fim).strftime("%H:%M")),
                "entrada": local(entrada).strftime("%H:%M") if entrada else False,
                "saida": local(saida).strftime("%H:%M") if saida else False,
                "atraso_min": atraso if atraso > TOLERANCIA_ATRASO_MIN else 0,
                "horas_escaladas": round(t.horas, 2), "horas_trabalhadas": round(trabalhadas, 2),
                "horas_extras": round(max(0.0, trabalhadas - t.horas), 2), "faltou": not presencas,
            }))
        self.linha_ids = linhas
        return {"type": "ir.actions.act_window", "res_model": self._name, "res_id": self.id, "view_mode": "form",
                "target": "new", "name": _("Escalado x trabalhado")}

    def action_csv(self):
        """Arquivo para a folha / contador."""
        self.ensure_one()
        if not self.linha_ids:
            self.action_gerar()
        saida = io.StringIO()
        escritor = csv.writer(saida, delimiter=";")
        escritor.writerow(["Pessoa", "Dia", "Turno", "Escalado", "Entrada", "Saída", "Atraso (min)",
                           "Horas escaladas", "Horas trabalhadas", "Horas extras", "Faltou"])
        for l in self.linha_ids:
            escritor.writerow([l.user_id.name, l.dia.strftime("%d/%m/%Y"), l.turno, l.escalado, l.entrada or "",
                               l.saida or "", l.atraso_min, ("%.2f" % l.horas_escaladas).replace(".", ","),
                               ("%.2f" % l.horas_trabalhadas).replace(".", ","), ("%.2f" % l.horas_extras).replace(".", ","),
                               "sim" if l.faltou else ""])
        anexo = self.env["ir.attachment"].create({
            "name": "ponto_%s_%s.csv" % (self.data_de, self.data_ate), "type": "binary", "mimetype": "text/csv",
            "datas": base64.b64encode(saida.getvalue().encode("utf-8-sig")), "res_model": self._name, "res_id": self.id})
        return {"type": "ir.actions.act_url", "url": "/web/content/%s?download=true" % anexo.id, "target": "self"}


class BotecoEscalaRelatorioLinha(models.TransientModel):
    _name = "boteco.escala.relatorio.linha"
    _description = "Linha do escalado x trabalhado"
    _order = "dia, user_id"

    relatorio_id = fields.Many2one("boteco.escala.relatorio", required=True, ondelete="cascade")
    user_id = fields.Many2one("res.users", string="Pessoa")
    dia = fields.Date()
    turno = fields.Char()
    escalado = fields.Char()
    entrada = fields.Char()
    saida = fields.Char("Saída")
    atraso_min = fields.Integer("Atraso (min)")
    horas_escaladas = fields.Float(digits=(5, 2))
    horas_trabalhadas = fields.Float(digits=(5, 2))
    horas_extras = fields.Float(digits=(5, 2))
    faltou = fields.Boolean()


class BotecoPinTentativa(models.Model):
    _inherit = "boteco.pin.tentativa"

    tipo = fields.Selection(selection_add=[("ponto", "Ponto")], ondelete={"ponto": "cascade"})
