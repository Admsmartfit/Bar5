from odoo import fields, models


class RestaurantTable(models.Model):
    _inherit = "restaurant.table"

    # Etapa 15: utensílios já levados à mesa nesta ocupação (zera quando a mesa fica livre)
    boteco_copos_enviados = fields.Integer("Copos de cerveja já levados", copy=False)
    boteco_tacas_enviadas = fields.Integer("Taças de vinho já levadas", copy=False)

    def _boteco_zerar_ocupacao(self):
        res = super()._boteco_zerar_ocupacao()
        marcadas = self.filtered(lambda m: m.boteco_copos_enviados or m.boteco_tacas_enviadas)
        if marcadas:
            marcadas.sudo().write({"boteco_copos_enviados": 0, "boteco_tacas_enviadas": 0})
        return res
