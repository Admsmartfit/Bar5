from odoo import fields, models


class BotecoSetor(models.Model):
    """Setor de produção: para onde vai cada item pedido (bar, chapa...)."""

    _name = "boteco.setor"
    _description = "Setor de produção"
    _order = "sequence, id"

    name = fields.Char("Nome", required=True, translate=True)
    codigo = fields.Char("Código", required=True, help="Identificador curto, ex.: bar, chapa.")
    sequence = fields.Integer(default=10)
    cor = fields.Char("Cor", default="#2563eb", help="Cor do setor nas telas (hexadecimal).")
    impressora_id = fields.Many2one(
        "boteco.impressora",
        string="Impressora de pedidos",
        domain="[('linguagem', '=', 'escpos')]",
        help="Tickets deste setor saem nesta impressora.",
    )
    company_id = fields.Many2one("res.company", default=lambda s: s.env.company)
    active = fields.Boolean(default=True)

    _sql_constraints = [
        ("codigo_unico", "unique(codigo, company_id)", "Já existe um setor com este código."),
    ]
