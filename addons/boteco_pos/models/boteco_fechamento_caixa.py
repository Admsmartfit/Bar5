from odoo import api, fields, models


class BotecoFechamentoCaixa(models.Model):
    """Contagem cega do fechamento: o que foi contado, o que era esperado e a diferença."""

    _name = "boteco.fechamento.caixa"
    _description = "Fechamento de caixa (contagem cega)"
    _order = "data desc, id desc"

    name = fields.Char(compute="_compute_name", store=True)
    session_id = fields.Many2one("pos.session", string="Sessão do caixa", required=True, index=True, ondelete="restrict")
    config_id = fields.Many2one(related="session_id.config_id", store=True)
    data = fields.Datetime(default=fields.Datetime.now, required=True)
    dia_operacao = fields.Date("Dia de operação", index=True)
    operador_id = fields.Many2one("res.users", string="Quem contou", default=lambda s: s.env.user)
    autorizado_por_id = fields.Many2one("res.users", string="Quem autorizou")
    linha_ids = fields.One2many("boteco.fechamento.caixa.linha", "fechamento_id", string="Formas de pagamento")
    total_esperado = fields.Monetary(compute="_compute_totais", store=True, currency_field="currency_id")
    total_contado = fields.Monetary(compute="_compute_totais", store=True, currency_field="currency_id")
    diferenca = fields.Monetary(compute="_compute_totais", store=True, currency_field="currency_id")
    observacao = fields.Text("Observação")
    company_id = fields.Many2one(related="session_id.company_id", store=True)
    currency_id = fields.Many2one(related="session_id.currency_id")

    @api.depends("session_id.name", "data")
    def _compute_name(self):
        for f in self:
            f.name = "Fechamento %s" % (f.session_id.name or "")

    @api.depends("linha_ids.esperado", "linha_ids.contado")
    def _compute_totais(self):
        for f in self:
            f.total_esperado = sum(f.linha_ids.mapped("esperado"))
            f.total_contado = sum(f.linha_ids.mapped("contado"))
            f.diferenca = f.total_contado - f.total_esperado

    def action_imprimir(self):
        return self.env.ref("boteco_pos.report_fechamento_caixa").report_action(self)


class BotecoFechamentoCaixaLinha(models.Model):
    _name = "boteco.fechamento.caixa.linha"
    _description = "Fechamento de caixa por forma de pagamento"
    _order = "sequence, id"

    fechamento_id = fields.Many2one("boteco.fechamento.caixa", required=True, ondelete="cascade")
    sequence = fields.Integer(default=10)
    payment_method_id = fields.Many2one("pos.payment.method", string="Forma de pagamento")
    nome = fields.Char("Forma", required=True)
    esperado = fields.Monetary(currency_field="currency_id")
    contado = fields.Monetary(currency_field="currency_id")
    diferenca = fields.Monetary(compute="_compute_diferenca", store=True, currency_field="currency_id")
    quantidade = fields.Integer("Pagamentos")
    currency_id = fields.Many2one(related="fechamento_id.currency_id")

    @api.depends("esperado", "contado")
    def _compute_diferenca(self):
        for linha in self:
            linha.diferenca = linha.contado - linha.esperado
