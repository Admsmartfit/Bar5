from odoo import fields, models


class PosNote(models.Model):
    _inherit = "pos.note"

    boteco_tag_rapida = fields.Boolean(
        "Tag rápida do boteco", help="Entra nos PDVs quando 'Tags rápidas' está ligado na Central de Recursos.")
