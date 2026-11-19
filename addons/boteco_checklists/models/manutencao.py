"""Manutenção preventiva (chopeira, freezers, coifa, gás, filtros, extintores) sobre o 'maintenance' gratuito."""

from datetime import datetime, time, timedelta

from odoo import _, api, fields, models

from .checklist import _tz

AVISO_DIAS = 3  # aviso antes de vencer

# (equipamento, o que fazer, a cada N, unidade)
PLANOS_PADRAO = [
    ("Chopeira", "Limpeza da chopeira e das linhas", 7, "day"),
    ("Filtro de água", "Troca do filtro de água", 6, "month"),
    ("Extintores", "Recarga / teste dos extintores", 12, "month"),
    ("Coifa e exaustor", "Limpeza da coifa e dos filtros de gordura", 1, "month"),
    ("Instalação de gás", "Teste de vazamento e mangueiras do gás", 6, "month"),
    ("Freezers e geladeiras", "Degelo e limpeza das borrachas", 1, "month"),
]


class ResCompany(models.Model):
    _inherit = "res.company"

    boteco_flag_checklists_appcc = fields.Boolean("Checklists de abertura/fechamento e APPCC", default=True)
    boteco_flag_manutencao_preventiva = fields.Boolean("Manutenção preventiva (chopeira, freezers, gás)", default=True)


class MaintenanceRequest(models.Model):
    _inherit = "maintenance.request"

    boteco_custo = fields.Monetary("Custo", currency_field="boteco_moeda_id")
    boteco_moeda_id = fields.Many2one(related="company_id.currency_id")


class MaintenanceEquipment(models.Model):
    _inherit = "maintenance.equipment"

    @api.model
    def _boteco_criar_planos(self):
        """Uma vez: equipamentos comuns de bar com o plano preventivo (o dono arquiva o que não tiver)."""
        Param = self.env["ir.config_parameter"].sudo()
        if Param.get_param("boteco.manutencao_planos_criados"):
            return True
        Pedido = self.env["maintenance.request"].sudo()
        agora = fields.Datetime.now()
        for nome, tarefa, intervalo, unidade in PLANOS_PADRAO:
            equipamento = self.sudo().search([("name", "=", nome)], limit=1) or self.sudo().create({"name": nome})
            if Pedido.search_count([("equipment_id", "=", equipamento.id), ("recurring_maintenance", "=", True)]):
                continue
            proxima = agora + (timedelta(days=intervalo) if unidade == "day" else timedelta(days=30 * intervalo))
            Pedido.create({"name": tarefa, "equipment_id": equipamento.id, "maintenance_type": "preventive",
                           "recurring_maintenance": True, "repeat_interval": intervalo, "repeat_unit": unidade,
                           "repeat_type": "forever", "schedule_date": proxima})
        Param.set_param("boteco.manutencao_planos_criados", "1")
        return True


class BotecoPainel(models.AbstractModel):
    _inherit = "boteco.painel"

    @api.model
    def _alertas_extras(self, company):
        alertas = super()._alertas_extras(company)
        if company.boteco_recurso_ativo("checklists_appcc"):
            hoje = datetime.now(_tz(company)).date()
            atrasados = self.env["boteco.checklist.execucao"].sudo().search(
                [("company_id", "=", company.id), ("data", "=", hoje), ("atrasado", "=", True)])
            for e in atrasados:
                alertas.append(_("Checklist atrasado: %s (era até %s).", e.name,
                                 fields.Datetime.context_timestamp(self, e.hora_limite).strftime("%H:%M")))
            abertas = self.env["boteco.nao.conformidade"].sudo().search_count(
                [("company_id", "=", company.id), ("estado", "=", "aberta")])
            if abertas:
                alertas.append(_("%s não conformidade(s) de boas práticas em aberto.", abertas))
        if company.boteco_recurso_ativo("manutencao_preventiva"):
            for pedido in self.env["boteco.checklists.manutencao"]._vencendo(company):
                quando = pedido.schedule_date.date()
                if quando < fields.Date.context_today(self):
                    alertas.append(_("Manutenção vencida: %(t)s (%(e)s), era %(d)s.", t=pedido.name,
                                     e=pedido.equipment_id.name, d=quando.strftime("%d/%m")))
                else:
                    alertas.append(_("Manutenção em %(d)s: %(t)s (%(e)s).", t=pedido.name, e=pedido.equipment_id.name,
                                     d=quando.strftime("%d/%m")))
        return alertas


class BotecoChecklistsManutencao(models.AbstractModel):
    _name = "boteco.checklists.manutencao"
    _description = "Avisos de manutenção preventiva"

    @api.model
    def _vencendo(self, company):
        limite = datetime.combine(fields.Date.context_today(self) + timedelta(days=AVISO_DIAS), time.max)
        return self.env["maintenance.request"].sudo().search([
            ("maintenance_type", "=", "preventive"), ("stage_id.done", "=", False), ("archive", "=", False),
            ("schedule_date", "!=", False), ("schedule_date", "<=", limite),
            "|", ("company_id", "=", company.id), ("company_id", "=", False),
        ], order="schedule_date")
