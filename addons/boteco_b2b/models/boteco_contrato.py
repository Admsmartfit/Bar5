from dateutil.relativedelta import relativedelta

from odoo import _, api, fields, models
from odoo.exceptions import UserError


class BotecoContratoAssessoria(models.Model):
    """Contrato de assessoria a outro bar: implantação + mensalidade (receita prevista no plano)."""

    _name = "boteco.contrato.assessoria"
    _description = "Contrato de assessoria"
    _inherit = ["mail.thread"]
    _order = "data_inicio desc"

    name = fields.Char("Contrato", required=True, default=lambda s: _("Novo contrato"), copy=False)
    partner_id = fields.Many2one("res.partner", string="Bar atendido", required=True, tracking=True)
    data_inicio = fields.Date("Início", required=True, default=fields.Date.context_today)
    dia_vencimento = fields.Integer("Dia de vencimento", default=10)
    valor_implantacao = fields.Monetary("Implantação", default=3500.0, currency_field="currency_id")
    valor_mensal = fields.Monetary("Mensalidade", default=450.0, currency_field="currency_id", tracking=True)
    estado = fields.Selection([("rascunho", "Em negociação"), ("ativo", "Ativo"), ("encerrado", "Encerrado")],
                              default="rascunho", required=True, tracking=True)
    proxima_competencia = fields.Date("Próxima mensalidade (mês)", readonly=True)
    fatura_ids = fields.One2many("account.move", "boteco_contrato_id", string="Cobranças")
    faturas_count = fields.Integer(compute="_compute_faturas_count")
    company_id = fields.Many2one("res.company", default=lambda s: s.env.company)
    currency_id = fields.Many2one(related="company_id.currency_id")

    def _compute_faturas_count(self):
        for c in self:
            c.faturas_count = len(c.fatura_ids)

    def _produto(self, xmlid):
        return self.env.ref("boteco_b2b.%s" % xmlid)

    def _criar_cobranca(self, produto, valor, descricao, competencia=None, vencimento=None):
        self.ensure_one()
        fatura = self.env["account.move"].create({
            "move_type": "out_invoice",
            "partner_id": self.partner_id.id,
            "boteco_frente": "assessoria",
            "boteco_contrato_id": self.id,
            "boteco_competencia": competencia,
            "invoice_date": fields.Date.context_today(self),
            "invoice_payment_term_id": False,  # vence no dia do contrato, não no prazo do cliente
            "invoice_date_due": vencimento or fields.Date.context_today(self),
            "invoice_line_ids": [fields.Command.create({
                "product_id": produto.id, "name": descricao, "quantity": 1, "price_unit": valor, "tax_ids": [],
            })],
        })
        fatura.action_post()
        return fatura

    def _vencimento(self, competencia):
        dia = min(max(self.dia_vencimento or 10, 1), 28)
        return competencia.replace(day=dia)

    def action_ativar(self):
        for c in self:
            if c.estado != "rascunho":
                raise UserError(_("O contrato já está ativo ou encerrado."))
            if c.name == _("Novo contrato"):
                c.name = self.env["ir.sequence"].next_by_code("boteco.contrato.assessoria") or c.name
            if c.valor_implantacao:
                c._criar_cobranca(c._produto("produto_implantacao"), c.valor_implantacao,
                                  _("Implantação do sistema e assessoria – %s", c.partner_id.name))
            primeira = c.data_inicio.replace(day=1)
            c.write({"estado": "ativo", "proxima_competencia": primeira})
        return True

    def action_encerrar(self):
        self.write({"estado": "encerrado"})
        return True

    def _gerar_mensalidades_ate(self, data_limite):
        """Gera as mensalidades cujo mês já começou (ou começa no mês seguinte ao limite)."""
        criadas = self.env["account.move"]
        for c in self.filtered(lambda x: x.estado == "ativo"):
            while c.proxima_competencia and c.proxima_competencia <= data_limite:
                competencia = c.proxima_competencia
                existe = c.fatura_ids.filtered(lambda f: f.boteco_competencia == competencia and f.state != "cancel")
                if not existe:
                    criadas |= c._criar_cobranca(
                        c._produto("produto_mensalidade"), c.valor_mensal,
                        _("Mensalidade de assessoria %(mes)s – %(bar)s", mes=competencia.strftime("%m/%Y"),
                          bar=c.partner_id.name),
                        competencia=competencia, vencimento=c._vencimento(competencia),
                    )
                c.proxima_competencia = competencia + relativedelta(months=1)
        return criadas

    @api.model
    def _cron_gerar_mensalidades(self):
        """Todo dia: garante a cobrança do mês seguinte já emitida (o bar recebe com antecedência)."""
        hoje = fields.Date.context_today(self)
        limite = (hoje + relativedelta(months=1)).replace(day=1)
        self.search([("estado", "=", "ativo")])._gerar_mensalidades_ate(limite)
        return True

    def action_ver_cobrancas(self):
        self.ensure_one()
        return {"type": "ir.actions.act_window", "res_model": "account.move", "view_mode": "list,form",
                "domain": [("boteco_contrato_id", "=", self.id)], "name": _("Cobranças")}
