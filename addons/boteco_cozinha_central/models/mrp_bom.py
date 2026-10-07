from odoo import api, fields, models


class MrpBom(models.Model):
    """Receita de produção da cozinha central (lista de materiais do tipo 'fabricar')."""

    _inherit = "mrp.bom"

    boteco_perda_esperada = fields.Float(
        "Perda esperada (%)", help="Quanto se perde no preparo (limpeza, cocção). Só informativo para comparar com o real.")
    boteco_modo_preparo = fields.Html("Modo de preparo")
    boteco_tempo_preparo_min = fields.Integer("Tempo de preparo (min)")

    @api.model_create_multi
    def create(self, vals_list):
        # Na cozinha o peso final varia: consumo flexível evita o aviso "consumiu diferente do previsto"
        for vals in vals_list:
            vals.setdefault("consumption", "flexible")
        return super().create(vals_list)
