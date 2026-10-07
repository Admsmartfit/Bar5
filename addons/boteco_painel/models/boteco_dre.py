"""DRE simples por frente do negócio: bar, tira-gosto B2B e assessoria."""

from dateutil.relativedelta import relativedelta

from odoo import _, api, fields, models

FRENTES = [("bar", "Bar"), ("b2b", "Tira-gosto B2B"), ("assessoria", "Assessoria")]


class BotecoDre(models.TransientModel):
    _name = "boteco.dre"
    _description = "DRE por frente"

    data_inicio = fields.Date("De", required=True, default=lambda s: fields.Date.context_today(s).replace(day=1))
    data_fim = fields.Date("Até", required=True,
                           default=lambda s: fields.Date.context_today(s).replace(day=1) + relativedelta(months=1, days=-1))
    company_id = fields.Many2one("res.company", default=lambda s: s.env.company, required=True)

    @api.model
    def calcular(self, inicio, fim, company=None):
        company = company or self.env.company
        resultado = {f: {"receita": 0.0, "custo": 0.0, "taxas_cartao": 0.0, "despesas": 0.0} for f, _n in FRENTES}

        # Bar: contas pagas no PDV (sem a taxa de serviço, que é repasse da equipe)
        pedidos = self.env["pos.order"].sudo().search([
            ("company_id", "=", company.id), ("state", "in", ("paid", "done", "invoiced")),
            ("boteco_dia_operacao", ">=", inicio), ("boteco_dia_operacao", "<=", fim),
        ])
        taxa_prod = pedidos.config_id.boteco_produto_taxa_id
        linhas = pedidos.lines.filtered(lambda l: l.product_id not in taxa_prod)
        resultado["bar"]["receita"] = sum(linhas.mapped("price_subtotal"))
        cmv = self.env["boteco.cmv"].sudo().search([("company_id", "=", company.id), ("dia", ">=", inicio), ("dia", "<=", fim)])
        resultado["bar"]["custo"] = sum(cmv.mapped("custo"))
        for pagamento in pedidos.payment_ids:
            resultado["bar"]["taxas_cartao"] += pagamento.amount * (pagamento.payment_method_id.boteco_taxa_pct or 0.0) / 100.0

        # B2B e assessoria: faturas emitidas no período
        Fatura = self.env["account.move"].sudo()
        faturas = Fatura.search([
            ("company_id", "=", company.id), ("state", "=", "posted"),
            ("move_type", "in", ("out_invoice", "out_refund")), ("boteco_frente", "in", ("b2b", "assessoria")),
            ("invoice_date", ">=", inicio), ("invoice_date", "<=", fim),
        ])
        for fatura in faturas:
            resultado[fatura.boteco_frente]["receita"] += fatura.amount_untaxed_signed
        # Custo do B2B: valor de estoque do que foi entregue aos bares clientes
        entregas = self.env["stock.move"].sudo().search([
            ("company_id", "=", company.id), ("state", "=", "done"), ("sale_line_id", "!=", False),
            ("location_dest_id.usage", "=", "customer"),
            ("date", ">=", fields.Datetime.to_datetime(inicio)),
            ("date", "<", fields.Datetime.to_datetime(fim) + relativedelta(days=1)),
        ]).filtered(lambda m: m.sale_line_id.order_id.partner_id.commercial_partner_id.boteco_cliente_b2b)
        resultado["b2b"]["custo"] = -sum(entregas.stock_valuation_layer_ids.mapped("value"))

        # Despesas (contas a pagar) marcadas por frente; "geral" fica separada
        contas = Fatura.search([
            ("company_id", "=", company.id), ("state", "=", "posted"), ("move_type", "in", ("in_invoice", "in_refund")),
            ("invoice_date", ">=", inicio), ("invoice_date", "<=", fim),
        ])
        despesas_gerais = 0.0
        for conta in contas:
            valor = -conta.amount_untaxed_signed
            if conta.boteco_frente in resultado:
                resultado[conta.boteco_frente]["despesas"] += valor
            else:
                despesas_gerais += valor

        for dados in resultado.values():
            dados["margem"] = dados["receita"] - dados["custo"]
            dados["resultado"] = dados["margem"] - dados["taxas_cartao"] - dados["despesas"]
        total = sum(d["resultado"] for d in resultado.values()) - despesas_gerais
        return {
            "inicio": fields.Date.to_string(inicio), "fim": fields.Date.to_string(fim),
            "frentes": [{"codigo": f, "nome": n, **{k: round(v, 2) for k, v in resultado[f].items()}} for f, n in FRENTES],
            "despesas_gerais": round(despesas_gerais, 2),
            "resultado_total": round(total, 2),
        }

    def action_imprimir(self):
        self.ensure_one()
        return self.env.ref("boteco_painel.report_dre").report_action(self)
