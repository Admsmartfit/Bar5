from datetime import datetime, time, timedelta

import pytz

from odoo import api, fields, models

TIPOS_UNIDADE = [
    ("bar", "Bar"),
    ("cozinha_central", "Cozinha central"),
    ("bar_e_cozinha", "Bar e cozinha central"),
]


class ResCompany(models.Model):
    _inherit = "res.company"

    boteco_tipo_unidade = fields.Selection(
        TIPOS_UNIDADE,
        string="Tipo de unidade",
        help="Como esta empresa aparece no boteco. Use 'Bar e cozinha central' quando o "
        "contador decidir por um CNPJ só (dois armazéns na mesma empresa).",
    )
    boteco_hora_virada = fields.Float(
        string="Hora em que o dia vira",
        default=6.0,
        help="O 'dia de operação' vai desta hora até a mesma hora do dia seguinte. "
        "Uma venda às 2h da madrugada de sábado conta na sexta.",
    )
    boteco_rede_clientes = fields.Char(
        string="Rede Wi-Fi dos clientes",
        help="Faixas de IP (ex.: 192.168.20.0/24) de onde o QR Code da mesa pode fazer pedido. "
        "Vazio = qualquer rede.",
    )
    boteco_rede_sistema = fields.Char(
        string="Rede do sistema",
        help="Faixas de IP dos aparelhos da equipe. A tela de login por PIN só aparece nelas. "
        "Vazio = qualquer rede.",
    )
    boteco_registro_sanitario = fields.Char(
        string="Registro sanitário",
        help="Número do registro na Vigilância Sanitária, impresso nas etiquetas.",
    )

    # ------------------------------------------------------------------
    # Dia de operação
    # ------------------------------------------------------------------
    def _boteco_tz(self):
        self.ensure_one()
        tz_name = self.partner_id.tz or self.env.user.tz or "America/Sao_Paulo"
        try:
            return pytz.timezone(tz_name)
        except pytz.UnknownTimeZoneError:
            return pytz.timezone("America/Sao_Paulo")

    def boteco_dia_operacao(self, momento=None):
        """Data do 'dia de operação' de um instante (UTC naive, como o Odoo guarda)."""
        self.ensure_one()
        momento = momento or fields.Datetime.now()
        tz = self._boteco_tz()
        local = pytz.utc.localize(momento).astimezone(tz)
        virada = timedelta(hours=self.boteco_hora_virada or 0.0)
        return (local - virada).date()

    def boteco_intervalo_dia(self, dia):
        """(inicio, fim) em UTC naive do dia de operação ``dia`` (date)."""
        self.ensure_one()
        tz = self._boteco_tz()
        horas = self.boteco_hora_virada or 0.0
        inicio_local = tz.localize(datetime.combine(dia, time.min) + timedelta(hours=horas))
        fim_local = inicio_local + timedelta(days=1)
        return (
            inicio_local.astimezone(pytz.utc).replace(tzinfo=None),
            fim_local.astimezone(pytz.utc).replace(tzinfo=None),
        )

    @api.model
    def boteco_agora_local(self):
        """Agora no fuso da empresa atual (datetime com tz)."""
        return pytz.utc.localize(fields.Datetime.now()).astimezone(self.env.company._boteco_tz())
