from odoo import fields, models, tools


class BotecoKdsTempo(models.Model):
    """Relatório de tempos de produção por produto e por hora da noite (somente leitura)."""

    _name = "boteco.kds.tempo"
    _description = "Tempos de produção"
    _auto = False
    _order = "criado_em desc"

    criado_em = fields.Datetime("Pedido em", readonly=True)
    dia = fields.Date("Dia", readonly=True)
    hora = fields.Integer("Hora da noite", readonly=True, help="Hora local (Brasília) em que o pedido chegou.")
    setor_id = fields.Many2one("boteco.setor", string="Setor", readonly=True)
    product_id = fields.Many2one("product.product", string="Produto", readonly=True)
    quantidade = fields.Float("Quantidade", readonly=True)
    minutos_preparo = fields.Float("Minutos até pronto", readonly=True, aggregator="avg")
    minutos_entrega = fields.Float("Minutos até entregue", readonly=True, aggregator="avg")
    atrasado = fields.Boolean("Passou de 30 min", readonly=True)
    company_id = fields.Many2one("res.company", readonly=True)

    def init(self):
        tools.drop_view_if_exists(self.env.cr, self._table)
        self.env.cr.execute(
            """
            CREATE OR REPLACE VIEW %s AS (
                SELECT
                    i.id AS id,
                    p.criado_em AS criado_em,
                    (p.criado_em AT TIME ZONE 'UTC' AT TIME ZONE 'America/Sao_Paulo')::date AS dia,
                    EXTRACT(HOUR FROM (p.criado_em AT TIME ZONE 'UTC' AT TIME ZONE 'America/Sao_Paulo'))::int AS hora,
                    p.setor_id AS setor_id,
                    i.product_id AS product_id,
                    i.quantidade AS quantidade,
                    CASE WHEN p.pronto_em IS NOT NULL
                         THEN EXTRACT(EPOCH FROM (p.pronto_em - p.criado_em)) / 60.0 END AS minutos_preparo,
                    CASE WHEN p.entregue_em IS NOT NULL
                         THEN EXTRACT(EPOCH FROM (p.entregue_em - p.criado_em)) / 60.0 END AS minutos_entrega,
                    (COALESCE(p.pronto_em, NOW() AT TIME ZONE 'UTC') - p.criado_em) > INTERVAL '30 minutes' AS atrasado,
                    p.company_id AS company_id
                FROM boteco_kds_item i
                JOIN boteco_kds_pedido p ON p.id = i.pedido_id
                WHERE p.tipo = 'novo' AND p.estado != 'cancelado'
            )
            """ % self._table
        )
