from odoo import api, fields, models


class PosPaymentMethod(models.Model):
    _inherit = "pos.payment.method"

    boteco_deeplink = fields.Char(
        "Link da maquininha (Smart POS)",
        help="Etapa 20: ao escolher esta forma de pagamento, o PDV abre o app da maquininha já com o valor. "
        "Use {valor} (12.34), {valor_centavos} (1234) e {pedido}. "
        "Ex.: app-da-maquininha://pagar?valor={valor_centavos}&ref={pedido}",
    )

    @api.model
    def _load_pos_data_fields(self, config_id):
        campos = super()._load_pos_data_fields(config_id)
        return campos + ["boteco_deeplink"] if campos else campos
