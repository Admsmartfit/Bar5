from odoo import fields, models

# Campos disponíveis numa linha da exportação plana (uma linha por item da nota)
CAMPOS = [
    ("registro_id", "Id do registro"), ("tipo", "Tipo (nfce/nfe)"), ("referencia", "Referência da venda"),
    ("data_hora", "Data e hora"), ("emitente_cnpj", "CNPJ do emitente"), ("emitente_razao", "Razão social"),
    ("emitente_ie", "IE do emitente"), ("cliente_documento", "CPF/CNPJ do cliente"), ("cliente_nome", "Nome do cliente"),
    ("item_codigo", "Código do item"), ("item_descricao", "Descrição"), ("item_ncm", "NCM"), ("item_cest", "CEST"),
    ("item_cfop", "CFOP"), ("item_cst_csosn", "CST/CSOSN"), ("item_origem", "Origem"), ("item_unidade", "Unidade"),
    ("item_quantidade", "Quantidade"), ("item_valor_unitario", "Valor unitário"), ("item_desconto", "Desconto"),
    ("item_valor_total", "Valor total do item"), ("taxa_servico", "Taxa de serviço"),
    ("pagamentos", "Formas de pagamento"), ("troco", "Troco"), ("valor_total", "Total da venda"),
]


class BotecoFiscalLayout(models.Model):
    """Ordem e nome das colunas da exportação, para casar com o sistema emissor escolhido."""

    _name = "boteco.fiscal.layout"
    _description = "Layout de exportação fiscal"

    name = fields.Char(required=True)
    separador = fields.Selection([(";", "Ponto e vírgula (;)"), (",", "Vírgula (,)"), ("\t", "Tabulação")], default=";")
    decimal_virgula = fields.Boolean("Decimal com vírgula", default=True)
    coluna_ids = fields.One2many("boteco.fiscal.layout.coluna", "layout_id", string="Colunas")
    active = fields.Boolean(default=True)

    def colunas(self):
        self.ensure_one()
        return [(c.campo, c.titulo or dict(CAMPOS)[c.campo]) for c in self.coluna_ids.sorted("sequence")]


class BotecoFiscalLayoutColuna(models.Model):
    _name = "boteco.fiscal.layout.coluna"
    _description = "Coluna do layout fiscal"
    _order = "sequence, id"

    layout_id = fields.Many2one("boteco.fiscal.layout", required=True, ondelete="cascade")
    sequence = fields.Integer(default=10)
    campo = fields.Selection(CAMPOS, required=True)
    titulo = fields.Char("Nome da coluna", help="Vazio = nome padrão.")
