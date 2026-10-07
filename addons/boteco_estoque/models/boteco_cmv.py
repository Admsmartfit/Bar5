from odoo import api, fields, models, tools

TIPOS = [
    ("venda", "Venda"),
    ("cortesia", "Cortesia"),
    ("funcionario", "Consumo de funcionário"),
    ("perda", "Perda"),
]


class BotecoCmv(models.Model):
    """CMV (custo da mercadoria vendida) por dia de operação, produto e categoria.

    Junta as linhas pagas do PDV (custo calculado pelo Odoo na baixa do estoque – inclui os
    insumos das fichas técnicas do tipo kit) e as perdas (sucata), que saem do estoque sem virar venda.
    """

    _name = "boteco.cmv"
    _description = "CMV"
    _auto = False
    _order = "dia desc"

    dia = fields.Date("Dia de operação", readonly=True)
    tipo = fields.Selection(TIPOS, readonly=True)
    product_id = fields.Many2one("product.product", string="Produto", readonly=True)
    categ_id = fields.Many2one("product.category", string="Categoria", readonly=True)
    quantidade = fields.Float(readonly=True)
    receita = fields.Float("Receita (sem taxa)", readonly=True)
    custo = fields.Float("Custo", readonly=True)
    margem = fields.Float("Margem", readonly=True)
    company_id = fields.Many2one("res.company", readonly=True)

    @api.model
    def _search(self, domain, offset=0, limit=None, order=None, **kwargs):
        # A view lê direto do banco: grava antes o que o ORM ainda tem pendente
        # (custo das linhas do PDV e valoração das perdas calculados na mesma transação).
        self.env.flush_all()
        return super()._search(domain, offset=offset, limit=limit, order=order, **kwargs)

    def init(self):
        tools.drop_view_if_exists(self.env.cr, self._table)
        self.env.cr.execute(
            """
            CREATE OR REPLACE VIEW boteco_cmv AS (
                -- id estável (o ORM busca ids e depois lê): linha do PDV = 2n, perda = 2n+1
                SELECT x.* FROM (
                    SELECT
                        l.id * 2 AS id,
                        o.boteco_dia_operacao AS dia,
                        CASE WHEN o.boteco_tipo_conta = 'funcionario' THEN 'funcionario'
                             WHEN l.boteco_cortesia THEN 'cortesia'
                             ELSE 'venda' END AS tipo,
                        l.product_id AS product_id,
                        pt.categ_id AS categ_id,
                        l.qty AS quantidade,
                        l.price_subtotal AS receita,
                        COALESCE(l.total_cost, 0.0) AS custo,
                        l.price_subtotal - COALESCE(l.total_cost, 0.0) AS margem,
                        o.company_id AS company_id
                    FROM pos_order_line l
                    JOIN pos_order o ON o.id = l.order_id
                    JOIN product_product pp ON pp.id = l.product_id
                    JOIN product_template pt ON pt.id = pp.product_tmpl_id
                    WHERE o.state IN ('paid', 'done', 'invoiced') AND pt.type != 'service'
                    UNION ALL
                    SELECT
                        s.id * 2 + 1 AS id,
                        ((s.date_done AT TIME ZONE 'UTC' AT TIME ZONE 'America/Sao_Paulo') - INTERVAL '6 hours')::date AS dia,
                        'perda' AS tipo,
                        s.product_id,
                        pt.categ_id,
                        s.scrap_qty AS quantidade,
                        0.0 AS receita,
                        COALESCE(-SUM(svl.value), 0.0) AS custo,
                        COALESCE(SUM(svl.value), 0.0) AS margem,
                        s.company_id
                    FROM stock_scrap s
                    JOIN product_product pp ON pp.id = s.product_id
                    JOIN product_template pt ON pt.id = pp.product_tmpl_id
                    LEFT JOIN stock_move m ON m.scrap_id = s.id
                    LEFT JOIN stock_valuation_layer svl ON svl.stock_move_id = m.id
                    WHERE s.state = 'done'
                    GROUP BY s.id, pt.categ_id
                ) x
            )
            """
        )

    @api.model
    def resumo_dia(self, dia, company=None):
        """Totais do dia: receita, custo, CMV % e saídas sem venda (usado no painel do dono)."""
        company = company or self.env.company
        linhas = self.search([("dia", "=", dia), ("company_id", "=", company.id)])
        vendas = linhas.filtered(lambda l: l.tipo == "venda")
        receita = sum(vendas.mapped("receita"))
        custo_vendas = sum(vendas.mapped("custo"))
        return {
            "receita": receita,
            "custo_vendas": custo_vendas,
            "cmv_pct": round(custo_vendas * 100 / receita, 1) if receita else 0.0,
            "custo_cortesias": sum(linhas.filtered(lambda l: l.tipo == "cortesia").mapped("custo")),
            "custo_funcionarios": sum(linhas.filtered(lambda l: l.tipo == "funcionario").mapped("custo")),
            "custo_perdas": sum(linhas.filtered(lambda l: l.tipo == "perda").mapped("custo")),
        }
