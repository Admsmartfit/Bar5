from odoo import fields, models


class PosConfig(models.Model):
    _inherit = "pos.config"

    boteco_limite_qr = fields.Monetary("Limite por pedido no QR", default=300.0,
                                       help="Pedido do celular acima deste valor precisa do garçom. Zero = sem limite.")
    boteco_exigir_rede = fields.Boolean("QR só pela rede do bar", default=True,
                                        help="O celular precisa estar no Wi-Fi dos clientes para pedir.")
    boteco_descanso_segundos = fields.Integer("Tela de descanso do tablet (s)", default=120)
