from odoo import fields, models

from .pix import payload_pix


class ResCompany(models.Model):
    _inherit = "res.company"

    # Central de Recursos (Etapa 27)
    boteco_flag_reservas_mesas = fields.Boolean("Reserva de mesas, lembretes e lista de espera", default=True)
    boteco_flag_reserva_sinal = fields.Boolean("Cobrar sinal (Pix) em reservas de grupo grande", default=False)

    boteco_reserva_faixas = fields.Char(
        "Horários de reserva", default="18:00, 18:30, 19:00, 19:30, 20:00, 20:30, 21:00, 21:30",
        help="Horários (hora do bar) que aparecem na página de reserva, separados por vírgula.",
    )
    boteco_reserva_permanencia_min = fields.Integer("Tempo médio na mesa (min)", default=120)
    boteco_reserva_tolerancia_min = fields.Integer("Tolerância de atraso (min)", default=15)
    boteco_reserva_max_pessoas = fields.Integer("Máximo de pessoas pela página", default=12,
                                                help="Grupos maiores falam com o bar. 0 = sem limite.")
    boteco_reserva_politica = fields.Text(
        "Política da reserva",
        default="Seguramos a mesa por 15 minutos depois do horário. Se não puder vir, cancele pelo link "
        "que mandamos: a mesa vai para quem está na lista de espera.",
    )
    boteco_reserva_sinal_min_pessoas = fields.Integer("Sinal a partir de (pessoas)", default=10)
    boteco_reserva_sinal_por_pessoa = fields.Float("Sinal por pessoa (R$)", default=20.0)
    boteco_reserva_pix_chave = fields.Char("Chave Pix do bar", help="Celular, e-mail, CNPJ ou chave aleatória.")

    def _boteco_pix_sinal(self, reserva):
        """Pix copia-e-cola do sinal (QR estático com valor e identificador da reserva)."""
        self.ensure_one()
        if not self.boteco_reserva_pix_chave or not reserva.sinal_valor:
            return ""
        return payload_pix(self.boteco_reserva_pix_chave, self.name, self.partner_id.city or "BRASIL",
                           reserva.sinal_valor, reserva.name)
