from odoo import fields, models

TIPOS_MOTIVO = [
    ("cancelamento", "Cancelamento de item"),
    ("desconto", "Desconto"),
    ("cortesia", "Cortesia"),
    ("perda", "Perda / quebra"),
    ("sangria", "Sangria"),
    ("reforco", "Reforço"),
    ("taxa", "Tirar taxa / couvert"),
]


class BotecoMotivo(models.Model):
    """Lista fechada de motivos: o garçom toca num botão em vez de digitar."""

    _name = "boteco.motivo"
    _description = "Motivo"
    _order = "tipo, sequence, id"

    name = fields.Char("Motivo", required=True, translate=True)
    tipo = fields.Selection(TIPOS_MOTIVO, required=True, index=True)
    sequence = fields.Integer(default=10)
    pede_detalhe = fields.Boolean("Pede explicação", help="Abre um campo de texto ao escolher este motivo.")
    active = fields.Boolean(default=True)
