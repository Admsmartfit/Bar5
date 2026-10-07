"""Plano de produção sugerido: o que produzir hoje na cozinha central."""

from datetime import timedelta

from odoo import _, api, fields, models
from odoo.exceptions import UserError

SEMANAS_HISTORICO = 4


class BotecoPlanoProducao(models.TransientModel):
    _name = "boteco.plano.producao"
    _description = "Plano de produção sugerido"

    data = fields.Date("Produzir para", default=fields.Date.context_today, required=True)
    linha_ids = fields.One2many("boteco.plano.producao.linha", "plano_id", string="Sugestões")

    @api.model
    def _saida_media_dia_semana(self, produto, data):
        """Média de saída (vendas no bar, B2B e consumo) no mesmo dia da semana das últimas semanas."""
        Move = self.env["stock.move"].sudo()
        total = 0.0
        for semana in range(1, SEMANAS_HISTORICO + 1):
            dia = data - timedelta(weeks=semana)
            inicio = fields.Datetime.to_datetime(dia)
            fim = inicio + timedelta(days=1)
            moves = Move.search([
                ("product_id", "=", produto.id), ("state", "=", "done"),
                ("date", ">=", inicio), ("date", "<", fim),
                ("location_id.usage", "=", "internal"),
                ("location_dest_id.usage", "in", ("customer", "production")),
            ])
            total += sum(moves.mapped("product_qty"))
        return total / SEMANAS_HISTORICO

    @api.model
    def _pedidos_b2b_abertos(self, produto, ate):
        linhas = self.env["sale.order.line"].sudo().search([
            ("product_id", "=", produto.id), ("order_id.state", "=", "sale"),
            ("order_id.commitment_date", "<=", fields.Datetime.to_datetime(ate) + timedelta(days=1)),
        ])
        return sum(max(l.product_uom_qty - l.qty_delivered, 0.0) for l in linhas)

    def action_calcular(self):
        self.ensure_one()
        produtos = self.env["product.product"].search([("boteco_produzido_cozinha", "=", True)])
        Bom = self.env["mrp.bom"]
        linhas = [fields.Command.clear()]
        for produto in produtos:
            bom = Bom._bom_find(produto, bom_type="normal").get(produto)
            dias = produto.boteco_dias_cobertura or 2
            media = self._saida_media_dia_semana(produto, self.data)
            b2b = self._pedidos_b2b_abertos(produto, self.data + timedelta(days=dias))
            estoque = produto.qty_available
            em_producao = sum(self.env["mrp.production"].search([
                ("product_id", "=", produto.id), ("state", "in", ("confirmed", "progress"))]).mapped("product_qty"))
            necessidade = media * dias + b2b - estoque - em_producao
            if bom and necessidade > 0:
                # Arredonda para receitas inteiras (ex.: receita rende 10 kg)
                lotes = -(-necessidade // (bom.product_qty or 1))
                sugerido = lotes * (bom.product_qty or 1)
            else:
                sugerido = max(necessidade, 0.0)
            linhas.append(fields.Command.create({
                "product_id": produto.id, "bom_id": bom.id if bom else False,
                "media_saida": media, "dias_cobertura": dias, "pedidos_b2b": b2b,
                "estoque": estoque, "em_producao": em_producao, "quantidade": sugerido,
            }))
        self.linha_ids = linhas
        return {"type": "ir.actions.act_window", "res_model": self._name, "res_id": self.id, "view_mode": "form",
                "target": "new"}

    def action_criar_producoes(self):
        self.ensure_one()
        criar = self.linha_ids.filtered(lambda l: l.quantidade > 0)
        if not criar:
            raise UserError(_("Nada a produzir pelo plano."))
        producoes = self.env["mrp.production"]
        for linha in criar:
            if not linha.bom_id:
                raise UserError(_("%s não tem receita de produção.", linha.product_id.display_name))
            producoes |= self.env["mrp.production"].create({
                "product_id": linha.product_id.id, "bom_id": linha.bom_id.id, "product_qty": linha.quantidade,
                "product_uom_id": linha.bom_id.product_uom_id.id,
                "date_start": fields.Datetime.to_datetime(self.data),
            })
        producoes.action_confirm()
        return {"type": "ir.actions.act_window", "res_model": "mrp.production", "view_mode": "list,form",
                "domain": [("id", "in", producoes.ids)], "name": _("Produções planejadas")}


class BotecoPlanoProducaoLinha(models.TransientModel):
    _name = "boteco.plano.producao.linha"
    _description = "Sugestão de produção"

    plano_id = fields.Many2one("boteco.plano.producao", required=True, ondelete="cascade")
    product_id = fields.Many2one("product.product", string="Produto", required=True)
    bom_id = fields.Many2one("mrp.bom", string="Receita")
    media_saida = fields.Float("Saída média/dia")
    dias_cobertura = fields.Integer("Dias")
    pedidos_b2b = fields.Float("Pedidos B2B")
    estoque = fields.Float("Em estoque")
    em_producao = fields.Float("Em produção")
    quantidade = fields.Float("Produzir")
