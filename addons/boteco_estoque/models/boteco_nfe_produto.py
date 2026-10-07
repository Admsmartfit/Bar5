from odoo import fields, models


class BotecoNfeProduto(models.Model):
    """De-para do produto do fornecedor (código na NF-e) para o insumo do boteco.

    Aprende sozinho: cada importação confirmada grava a relação, e na próxima nota do mesmo
    fornecedor nada precisa ser digitado. O fator converte a unidade da nota (ex.: caixa com 12)
    na unidade do estoque (unidade).
    """

    _name = "boteco.nfe.produto"
    _description = "Produto do fornecedor (NF-e)"
    _rec_name = "descricao"

    partner_id = fields.Many2one("res.partner", string="Fornecedor", required=True, index=True, ondelete="cascade")
    codigo = fields.Char("Código do fornecedor", required=True, index=True)
    descricao = fields.Char("Descrição na nota")
    product_id = fields.Many2one("product.product", string="Insumo", required=True, ondelete="cascade")
    fator = fields.Float("Unidades por item da nota", default=1.0,
                         help="Ex.: a nota diz 1 CX e a caixa tem 12 latas -> 12.")

    _sql_constraints = [
        ("codigo_unico", "unique(partner_id, codigo)", "Este código do fornecedor já está ligado a um insumo."),
    ]
