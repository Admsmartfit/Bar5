"""Histórico de cotações e radar de preços interessantes (Etapa 18)."""

from datetime import timedelta

from odoo import api, fields, models

DIAS_MEDIA = 60
DIAS_MINIMO = 90
QUEDA_INTERESSANTE = 10.0  # % abaixo da média móvel

ORIGENS = [
    ("nfe", "NF-e de compra"),
    ("orcamento_pdf", "Orçamento em PDF"),
    ("orcamento_imagem", "Foto de orçamento/encarte"),
    ("orcamento_texto", "Texto colado (WhatsApp)"),
    ("instagram", "Post no Instagram"),
    ("manual", "Digitado"),
]


class BotecoHistoricoPreco(models.Model):
    _name = "boteco.historico.preco"
    _description = "Histórico de preços de compra"
    _order = "data desc, id desc"
    _rec_name = "product_id"

    product_id = fields.Many2one("product.product", string="Insumo", required=True, index=True, ondelete="cascade")
    partner_id = fields.Many2one("res.partner", string="Fornecedor", index=True)
    data = fields.Date(default=fields.Date.context_today, required=True, index=True)
    preco_unitario = fields.Float("Preço por unidade", digits="Product Price", required=True,
                                  help="Preço por unidade de estoque do insumo (ex.: por kg).")
    origem = fields.Selection(ORIGENS, default="manual", required=True)
    referencia = fields.Char("Referência", help="Número da nota, nome do arquivo ou link do post.")
    descricao_original = fields.Char("Como veio escrito")
    company_id = fields.Many2one("res.company", default=lambda s: s.env.company, required=True)
    # Radar (calculado na entrada, contra o histórico anterior)
    media_60d = fields.Float("Média 60 dias", digits="Product Price", readonly=True)
    minimo_90d = fields.Float("Menor preço 90 dias", digits="Product Price", readonly=True)
    variacao_pct = fields.Float("Variação vs. média (%)", readonly=True)
    preco_interessante = fields.Boolean("Preço interessante", readonly=True, index=True,
                                        help="Pelo menos 10% abaixo da média dos últimos 60 dias.")

    @api.model_create_multi
    def create(self, vals_list):
        registros = super().create(vals_list)
        registros._calcular_radar()
        return registros

    def _calcular_radar(self):
        for registro in self:
            anteriores = self.search([
                ("product_id", "=", registro.product_id.id), ("company_id", "=", registro.company_id.id),
                ("id", "!=", registro.id), ("data", "<=", registro.data),
                ("data", ">=", registro.data - timedelta(days=DIAS_MINIMO)),
            ])
            janela_media = anteriores.filtered(lambda r: r.data >= registro.data - timedelta(days=DIAS_MEDIA))
            media = (sum(janela_media.mapped("preco_unitario")) / len(janela_media)) if janela_media else 0.0
            minimo = min(anteriores.mapped("preco_unitario")) if anteriores else 0.0
            variacao = ((registro.preco_unitario - media) * 100.0 / media) if media else 0.0
            ligado = registro.company_id.boteco_recurso_ativo("radar_precos_oportunidade")
            registro.write({
                "media_60d": media,
                "minimo_90d": minimo,
                "variacao_pct": variacao,
                "preco_interessante": bool(ligado and media and variacao <= -QUEDA_INTERESSANTE),
            })

    @api.model
    def registrar(self, produto, preco, fornecedor=None, origem="manual", referencia=None, data=None, descricao=None):
        """Grava uma cotação, se o radar estiver ligado. Devolve o registro (ou vazio)."""
        if not produto or preco <= 0 or not self.env.company.boteco_recurso_ativo("radar_precos_oportunidade"):
            return self.browse()
        return self.sudo().create({
            "product_id": produto.id, "partner_id": fornecedor.id if fornecedor else False,
            "preco_unitario": preco, "origem": origem, "referencia": referencia or False,
            "data": data or fields.Date.context_today(self), "descricao_original": descricao or False,
        })

    @api.model
    def melhor_fornecedor(self, produto, dias=30):
        """Cotação mais barata recente do insumo: (fornecedor, preço) ou (None, 0)."""
        recentes = self.search([
            ("product_id", "=", produto.id), ("partner_id", "!=", False), ("company_id", "=", self.env.company.id),
            ("data", ">=", fields.Date.context_today(self) - timedelta(days=dias)),
        ], order="preco_unitario asc, data desc", limit=1)
        return (recentes.partner_id, recentes.preco_unitario) if recentes else (None, 0.0)

    @api.model
    def oportunidades(self, dias=7):
        """Preços interessantes recentes (o mais barato de cada insumo)."""
        registros = self.search([
            ("preco_interessante", "=", True), ("company_id", "=", self.env.company.id),
            ("data", ">=", fields.Date.context_today(self) - timedelta(days=dias)),
        ], order="variacao_pct asc")
        vistos, resultado = set(), self.browse()
        for r in registros:
            if r.product_id.id not in vistos:
                vistos.add(r.product_id.id)
                resultado |= r
        return resultado
