from odoo import api, fields, models


class BotecoFiscalLote(models.Model):
    """Lote numerado de exportação: o que foi mandado para o sistema emissor e quando."""

    _name = "boteco.fiscal.lote"
    _description = "Lote de exportação fiscal"
    _order = "id desc"

    name = fields.Char("Lote", required=True, readonly=True,
                       default=lambda s: s.env["ir.sequence"].next_by_code("boteco.fiscal.lote") or "/")
    data = fields.Datetime(default=fields.Datetime.now, readonly=True)
    usuario_id = fields.Many2one("res.users", default=lambda s: s.env.user, readonly=True)
    periodo_inicio = fields.Date(readonly=True)
    periodo_fim = fields.Date(readonly=True)
    formato = fields.Selection([("csv", "CSV"), ("xlsx", "Excel"), ("json", "JSON")], readonly=True)
    reexportacao = fields.Boolean("Reexportação", readonly=True)
    registro_ids = fields.Many2many("boteco.fiscal.registro", string="Registros", readonly=True)
    quantidade = fields.Integer(compute="_compute_totais", store=True)
    valor_total = fields.Float(compute="_compute_totais", store=True)
    arquivo = fields.Binary(readonly=True, attachment=True)
    nome_arquivo = fields.Char(readonly=True)
    company_id = fields.Many2one("res.company", default=lambda s: s.env.company)

    @api.depends("registro_ids", "registro_ids.valor_total")
    def _compute_totais(self):
        for lote in self:
            lote.quantidade = len(lote.registro_ids)
            lote.valor_total = sum(lote.registro_ids.mapped("valor_total"))

    def action_baixar(self):
        self.ensure_one()
        return {"type": "ir.actions.act_url", "target": "self",
                "url": "/web/content/%s/%s/arquivo/%s?download=true" % (self._name, self.id, self.nome_arquivo)}
