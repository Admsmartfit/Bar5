"""Reserva de mesas, lembretes, lista de espera e no-show (Etapa 27)."""

import secrets
from datetime import datetime, time, timedelta

import pytz

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError

from odoo.addons.boteco_pos.models.boteco_crm import link_whatsapp

ATIVAS = ("pendente", "confirmada", "chegou")
ESTADOS = [
    ("pendente", "Aguardando sinal"),
    ("confirmada", "Confirmada"),
    ("chegou", "Chegou"),
    ("no_show", "Não veio (no-show)"),
    ("cancelada", "Cancelada"),
]
ORIGENS = [("link", "Página de reserva"), ("whatsapp", "WhatsApp"), ("telefone", "Telefone"), ("balcao", "Balcão")]


def _tz(company):
    return pytz.timezone(company.partner_id.tz or "America/Sao_Paulo")


def local_para_utc(company, dia, hora_texto):
    """'2026-11-20' + '20:30' (hora do bar) -> datetime UTC sem fuso (como o Odoo guarda)."""
    h, m = (int(x) for x in hora_texto.split(":"))
    local = _tz(company).localize(datetime.combine(dia, time(h, m)))
    return local.astimezone(pytz.utc).replace(tzinfo=None)


def utc_para_local(company, quando):
    return pytz.utc.localize(quando).astimezone(_tz(company))


class BotecoReserva(models.Model):
    _name = "boteco.reserva"
    _description = "Reserva de mesa"
    _order = "data_hora, id"

    name = fields.Char("Código", readonly=True, copy=False, default=lambda s: _("Nova"))
    cliente_nome = fields.Char("Nome", required=True)
    celular = fields.Char("Celular", required=True)
    partner_id = fields.Many2one("res.partner", string="Cliente", index=True)
    data_hora = fields.Datetime("Dia e hora", required=True, index=True)
    data_fim = fields.Datetime("Libera a mesa às", compute="_compute_data_fim", store=True, index=True)
    pessoas = fields.Integer("Pessoas", required=True, default=2)
    mesa_ids = fields.Many2many("restaurant.table", string="Mesas")
    mesas_texto = fields.Char("Mesa(s)", compute="_compute_mesas_texto")
    origem = fields.Selection(ORIGENS, default="telefone", required=True)
    estado = fields.Selection(ESTADOS, default="confirmada", required=True, index=True)
    observacao = fields.Char("Observação", help="Aniversário, cadeirinha, acessibilidade…")
    token = fields.Char(copy=False, index=True, default=lambda s: secrets.token_urlsafe(16))
    ip = fields.Char(copy=False)
    sinal_valor = fields.Monetary("Sinal", currency_field="currency_id")
    sinal_pago = fields.Boolean("Sinal recebido")
    currency_id = fields.Many2one(related="company_id.currency_id")
    lembrete_pendente = fields.Selection([("d1", "Véspera"), ("3h", "3 horas antes")], copy=False, index=True)
    lembrete_d1_feito = fields.Boolean(copy=False)
    lembrete_3h_feito = fields.Boolean(copy=False)
    chegou_em = fields.Datetime(copy=False)
    company_id = fields.Many2one("res.company", required=True, default=lambda s: s.env.company, index=True)

    @api.depends("data_hora", "company_id.boteco_reserva_permanencia_min")
    def _compute_data_fim(self):
        for r in self:
            minutos = r.company_id.boteco_reserva_permanencia_min or 120
            r.data_fim = r.data_hora + timedelta(minutes=minutos) if r.data_hora else False

    @api.depends("mesa_ids")
    def _compute_mesas_texto(self):
        for r in self:
            r.mesas_texto = " + ".join(str(m.table_number) for m in r.mesa_ids.sorted("table_number"))

    @api.constrains("pessoas")
    def _check_pessoas(self):
        if any(r.pessoas < 1 for r in self):
            raise ValidationError(_("A reserva precisa de pelo menos 1 pessoa."))

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("name", _("Nova")) == _("Nova"):
                vals["name"] = self.env["ir.sequence"].sudo().next_by_code("boteco.reserva") or _("Nova")
        reservas = super().create(vals_list)
        for r in reservas:
            if not r.partner_id:
                r.partner_id = r._boteco_cliente()
            if not r.mesa_ids and r.estado in ATIVAS:
                r.mesa_ids = r._boteco_alocar_mesas()
        reservas._boteco_avisar_mapa()
        return reservas

    def write(self, vals):
        res = super().write(vals)
        if {"estado", "mesa_ids", "data_hora", "pessoas"} & set(vals):
            self._boteco_avisar_mapa()
        return res

    # ------------------------------------------------------------------ cliente
    def _boteco_cliente(self):
        """Cliente pelo celular (sem cadastro extra): acha ou cria."""
        self.ensure_one()
        digitos = "".join(c for c in self.celular or "" if c.isdigit())
        Parceiro = self.env["res.partner"].sudo()
        if digitos:
            for p in Parceiro.search(["|", ("mobile", "ilike", digitos[-8:]), ("phone", "ilike", digitos[-8:])], limit=5):
                if "".join(c for c in (p.mobile or p.phone or "") if c.isdigit()).endswith(digitos[-8:]):
                    return p
        return Parceiro.create({"name": self.cliente_nome, "mobile": self.celular})

    # ------------------------------------------------------------------ disponibilidade
    @api.model
    def _boteco_mesas_reservaveis(self, company):
        configs = self.env["pos.config"].sudo().search([("company_id", "=", company.id)])
        mesas = configs.mapped("floor_ids.table_ids").filtered(lambda m: m.active and m.boteco_reservavel)
        return mesas.sorted(lambda m: (m.seats, m.table_number))

    @api.model
    def _boteco_mesas_ocupadas(self, company, inicio, fim, exceto=None):
        dominio = [("company_id", "=", company.id), ("estado", "in", ATIVAS),
                   ("data_hora", "<", fim), ("data_fim", ">", inicio)]
        if exceto:
            dominio.append(("id", "not in", exceto.ids))
        return self.sudo().search(dominio).mesa_ids

    @api.model
    def _boteco_escolher_mesas(self, company, inicio, pessoas, exceto=None):
        """A menor mesa que caiba; se nenhuma couber sozinha, junta até 3 mesas (Etapa 13)."""
        fim = inicio + timedelta(minutes=company.boteco_reserva_permanencia_min or 120)
        livres = self._boteco_mesas_reservaveis(company) - self._boteco_mesas_ocupadas(company, inicio, fim, exceto)
        for mesa in livres:
            if (mesa.seats or 0) >= pessoas:
                return mesa
        juntas = self.env["restaurant.table"]
        for mesa in livres.sorted(lambda m: -(m.seats or 0))[:3]:
            juntas |= mesa
            if sum(juntas.mapped("seats")) >= pessoas:
                return juntas
        return self.env["restaurant.table"]

    def _boteco_alocar_mesas(self):
        self.ensure_one()
        mesas = self._boteco_escolher_mesas(self.company_id, self.data_hora, self.pessoas, exceto=self)
        if not mesas:
            raise UserError(_("Não há mesa livre para %(p)s pessoas nesse horário.", p=self.pessoas))
        return mesas

    @api.model
    def _boteco_faixas(self, company):
        faixas = []
        for parte in (company.boteco_reserva_faixas or "").replace(";", ",").split(","):
            parte = parte.strip()
            if len(parte) == 5 and parte[2] == ":" and parte.replace(":", "").isdigit():
                faixas.append(parte)
        return faixas

    @api.model
    def boteco_disponibilidade(self, company, dia, pessoas):
        """Faixas do dia com mesa para `pessoas` (as que já passaram não aparecem)."""
        agora = fields.Datetime.now()
        resultado = []
        for faixa in self._boteco_faixas(company):
            inicio = local_para_utc(company, dia, faixa)
            if inicio <= agora:
                continue
            resultado.append({"faixa": faixa, "livre": bool(self._boteco_escolher_mesas(company, inicio, pessoas))})
        return resultado

    def _boteco_precisa_sinal(self):
        self.ensure_one()
        company = self.company_id
        minimo = company.boteco_reserva_sinal_min_pessoas or 0
        return company.boteco_recurso_ativo("reserva_sinal") and minimo and self.pessoas >= minimo

    @api.model
    def boteco_reservar(self, company, dados, origem="link", ip=None):
        """Usado pela página pública e pelo atendente: cria já com mesa, ou erro se lotou."""
        if not company.boteco_recurso_ativo("reservas_mesas"):
            raise UserError(_("Reservas indisponíveis."))
        dia = fields.Date.to_date(dados["dia"])
        inicio = local_para_utc(company, dia, dados["faixa"])
        if inicio <= fields.Datetime.now():
            raise UserError(_("Esse horário já passou."))
        if dados["faixa"] not in self._boteco_faixas(company):
            raise UserError(_("Horário fora das faixas de reserva."))
        pessoas = int(dados.get("pessoas") or 0)
        maximo = company.boteco_reserva_max_pessoas or 0
        if maximo and pessoas > maximo:
            raise UserError(_("Para mais de %(m)s pessoas, fale com a gente pelo WhatsApp.", m=maximo))
        mesas = self._boteco_escolher_mesas(company, inicio, pessoas)
        if not mesas:
            raise UserError(_("Esse horário lotou para %(p)s pessoas.", p=pessoas))
        reserva = self.sudo().create({
            "cliente_nome": (dados.get("nome") or "").strip()[:80], "celular": (dados.get("celular") or "").strip()[:30],
            "data_hora": inicio, "pessoas": pessoas, "mesa_ids": [fields.Command.set(mesas.ids)],
            "origem": origem, "observacao": (dados.get("observacao") or "").strip()[:200] or False,
            "ip": ip, "company_id": company.id,
        })
        if reserva._boteco_precisa_sinal():
            reserva.write({"estado": "pendente",
                           "sinal_valor": (company.boteco_reserva_sinal_por_pessoa or 0.0) * pessoas})
        return reserva

    # ------------------------------------------------------------------ ações
    def action_confirmar(self):
        for r in self:
            if r.estado not in ("pendente", "cancelada"):
                continue
            mesas = r.mesa_ids or r._boteco_alocar_mesas()
            r.write({"estado": "confirmada", "mesa_ids": [fields.Command.set(mesas.ids)]})
        return True

    def action_sinal_recebido(self):
        self.write({"sinal_pago": True})
        return self.action_confirmar()

    def action_chegou(self):
        """Garçom marca 'Chegou': a mesa abre já com o número de pessoas da reserva (Etapa 13)."""
        for r in self.filtered(lambda x: x.estado in ("pendente", "confirmada")):
            r.write({"estado": "chegou", "chegou_em": fields.Datetime.now()})
            por_mesa = max(r.pessoas // max(len(r.mesa_ids), 1), 1)
            for mesa in r.mesa_ids:
                mesa.sudo().boteco_definir_clientes(por_mesa)
            if r.sinal_pago and r.sinal_valor:
                r._boteco_alerta_pdv(_("Mesa %(m)s: reserva de %(n)s com sinal de R$ %(v).2f já pago. Desconte na conta.",
                                       m=r.mesas_texto, n=r.cliente_nome, v=r.sinal_valor))
        return True

    def action_cancelar(self):
        livres = self.filtered(lambda r: r.estado in ("pendente", "confirmada"))
        livres.write({"estado": "cancelada", "lembrete_pendente": False})
        for r in livres:
            r._boteco_oferecer_vaga()
        return True

    def action_no_show(self):
        self.filtered(lambda r: r.estado in ("pendente", "confirmada")).write(
            {"estado": "no_show", "lembrete_pendente": False})
        return True

    def action_abrir_whatsapp(self):
        """Lembrete pelo WhatsApp de quem está atendendo (link pronto, sem robô)."""
        self.ensure_one()
        if not self.celular:
            raise UserError(_("Reserva sem celular."))
        if self.lembrete_pendente == "d1":
            self.write({"lembrete_d1_feito": True, "lembrete_pendente": False})
        elif self.lembrete_pendente == "3h":
            self.write({"lembrete_3h_feito": True, "lembrete_pendente": False})
        return {"type": "ir.actions.act_url", "url": link_whatsapp(self.celular, self._boteco_mensagem()), "target": "new"}

    # ------------------------------------------------------------------ mensagens
    def _boteco_link_gerenciar(self):
        self.ensure_one()
        return "%s/reservar/%s" % (self.get_base_url(), self.token)

    def _boteco_quando(self):
        self.ensure_one()
        local = utc_para_local(self.company_id, self.data_hora)
        return local.strftime("%d/%m às %H:%M")

    def _boteco_mensagem(self):
        self.ensure_one()
        nome = (self.cliente_nome or "").split(" ")[0]
        tolerancia = self.company_id.boteco_reserva_tolerancia_min or 15
        return _(
            "Olá, %(n)s! Sua reserva no %(bar)s: %(q)s, %(p)s pessoas. Seguramos a mesa por %(t)s minutos. "
            "Confirme ou cancele aqui: %(link)s",
            n=nome, bar=self.company_id.name, q=self._boteco_quando(), p=self.pessoas, t=tolerancia,
            link=self._boteco_link_gerenciar(),
        )

    def _boteco_alerta_pdv(self, mensagem):
        for config in self.mesa_ids.floor_id.pos_config_ids:
            if config.current_session_id:
                config._notify("BOTECO_ALERTA", {"mensagem": mensagem, "tipo": "reserva"})

    def _boteco_avisar_mapa(self):
        mesas = self.mapped("mesa_ids")
        configs = mesas.floor_id.pos_config_ids.filtered("current_session_id")
        for config in configs:
            config._notify("BOTECO_RESERVA", {"mesas": mesas.ids})

    def _boteco_oferecer_vaga(self):
        """Cancelou: oferece a vaga ao 1º da lista de espera que cabe nas mesas liberadas."""
        self.ensure_one()
        lugares = sum(self.mesa_ids.mapped("seats"))
        local = utc_para_local(self.company_id, self.data_hora)
        espera = self.env["boteco.reserva.espera"].sudo().search([
            ("company_id", "=", self.company_id.id), ("estado", "=", "aguardando"),
            ("dia", "=", local.date()), ("pessoas", "<=", lugares or self.pessoas),
        ], order="create_date, id", limit=1)
        if espera:
            espera.write({"estado": "oferecida", "faixa_oferecida": local.strftime("%H:%M")})
            self._boteco_alerta_pdv(_("Vaga liberada %(q)s: avise %(n)s da lista de espera.",
                                      q=self._boteco_quando(), n=espera.nome))
        return espera

    # ------------------------------------------------------------------ crons
    @api.model
    def _cron_lembretes(self):
        """Véspera (20 a 28 h antes) e 3 horas antes: o lembrete aparece na lista para o atendente enviar."""
        agora = fields.Datetime.now()
        base = [("estado", "=", "confirmada"), ("lembrete_pendente", "=", False)]
        d1 = self.sudo().search(base + [("lembrete_d1_feito", "=", False), ("lembrete_3h_feito", "=", False),
                                        ("data_hora", ">", agora + timedelta(hours=20)),
                                        ("data_hora", "<=", agora + timedelta(hours=28))])
        d1.filtered(lambda r: r.company_id.boteco_recurso_ativo("reservas_mesas")).write({"lembrete_pendente": "d1"})
        h3 = self.sudo().search(base + [("lembrete_3h_feito", "=", False), ("data_hora", ">", agora),
                                        ("data_hora", "<=", agora + timedelta(hours=3))])
        h3.filtered(lambda r: r.company_id.boteco_recurso_ativo("reservas_mesas")).write({"lembrete_pendente": "3h"})
        return True

    @api.model
    def _cron_no_show(self):
        """Passou a tolerância sem 'Chegou': no-show e mesa liberada. Sinal não pago em 24 h: cancela."""
        agora = fields.Datetime.now()
        for r in self.sudo().search([("estado", "in", ("pendente", "confirmada")), ("data_hora", "<", agora)]):
            if not r.company_id.boteco_recurso_ativo("reservas_mesas"):
                continue
            if r.data_hora + timedelta(minutes=r.company_id.boteco_reserva_tolerancia_min or 15) < agora:
                r.action_no_show()
        prazo = agora - timedelta(hours=24)
        self.sudo().search([("estado", "=", "pendente"), ("sinal_pago", "=", False),
                            ("create_date", "<", prazo)]).action_cancelar()
        return True


class BotecoReservaEspera(models.Model):
    _name = "boteco.reserva.espera"
    _description = "Lista de espera de reservas"
    _order = "dia, create_date, id"

    nome = fields.Char(required=True)
    celular = fields.Char(required=True)
    dia = fields.Date(required=True, index=True)
    faixa = fields.Char("Horário desejado")
    faixa_oferecida = fields.Char("Horário oferecido")
    pessoas = fields.Integer(required=True, default=2)
    estado = fields.Selection([("aguardando", "Aguardando"), ("oferecida", "Vaga oferecida"),
                               ("atendida", "Virou reserva"), ("desistiu", "Desistiu")],
                              default="aguardando", required=True, index=True)
    company_id = fields.Many2one("res.company", required=True, default=lambda s: s.env.company)

    def _boteco_mensagem(self):
        self.ensure_one()
        return _("Olá, %(n)s! Abriu uma mesa para %(p)s pessoas no %(bar)s em %(d)s às %(h)s. Quer? Responda aqui.",
                 n=(self.nome or "").split(" ")[0], p=self.pessoas, bar=self.company_id.name,
                 d=self.dia.strftime("%d/%m"), h=self.faixa_oferecida or self.faixa or "")

    def action_abrir_whatsapp(self):
        self.ensure_one()
        return {"type": "ir.actions.act_url", "url": link_whatsapp(self.celular, self._boteco_mensagem()), "target": "new"}

    def action_virou_reserva(self):
        self.write({"estado": "atendida"})

    def action_desistiu(self):
        self.write({"estado": "desistiu"})


class RestaurantTable(models.Model):
    _inherit = "restaurant.table"

    boteco_reservavel = fields.Boolean("Aceita reserva", default=True)

    @api.model
    def boteco_reservas_mapa(self, config_id):
        """Mapa do salão: a próxima reserva de cada mesa (de 30 min atrás até as próximas 4 h)."""
        config = self.env["pos.config"].browse(config_id)
        company = config.company_id
        if not company.boteco_recurso_ativo("reservas_mesas"):
            return {}
        agora = fields.Datetime.now()
        reservas = self.env["boteco.reserva"].sudo().search([
            ("company_id", "=", company.id), ("estado", "in", ("pendente", "confirmada")),
            ("data_hora", ">=", agora - timedelta(minutes=company.boteco_reserva_tolerancia_min or 15)),
            ("data_hora", "<=", agora + timedelta(hours=4)),
        ], order="data_hora")
        mapa = {}
        for r in reservas:
            local = utc_para_local(company, r.data_hora)
            for mesa in r.mesa_ids:
                mapa.setdefault(str(mesa.id), {
                    "id": r.id, "hora": local.strftime("%H:%M"), "nome": (r.cliente_nome or "").split(" ")[0],
                    "pessoas": r.pessoas, "minutos": int((r.data_hora - agora).total_seconds() // 60),
                    "estado": r.estado,
                })
        return mapa

    def boteco_reserva_chegou(self):
        """Mesa reservada aberta no PDV: marca 'Chegou' e devolve quantas pessoas são."""
        self.ensure_one()
        mapa = self.boteco_reservas_mapa(self.floor_id.pos_config_ids[:1].id)
        info = mapa.get(str(self.id))
        if not info:
            return False
        reserva = self.env["boteco.reserva"].sudo().browse(info["id"])
        reserva.action_chegou()
        return {"pessoas": max(reserva.pessoas // max(len(reserva.mesa_ids), 1), 1), "nome": reserva.cliente_nome}


class ResPartner(models.Model):
    _inherit = "res.partner"

    boteco_no_shows = fields.Integer("Faltou a reservas", compute="_compute_boteco_no_shows")

    def _compute_boteco_no_shows(self):
        dados = self.env["boteco.reserva"].sudo()._read_group(
            [("partner_id", "in", self.ids), ("estado", "=", "no_show")], ["partner_id"], ["__count"])
        contagem = {p.id: n for p, n in dados}
        for parceiro in self:
            parceiro.boteco_no_shows = contagem.get(parceiro.id, 0)
