"""Plano de produção sugerido: o que produzir hoje na cozinha central.

Etapa 17 (Central de Recursos):
* capacidade_finita_congelados: limita por item (máximo/dia) e pela cozinha (kg/dia);
* controle_volume_freezer: não sugere o que não cabe no freezer;
* reserva_estoque_bar_b2b: a reserva mínima do bar entra na meta de estoque;
* explosao_insumos_fator_coccao: avisa quais matérias-primas faltam antes de ligar o fogão.
"""

import math
from datetime import timedelta

from odoo import _, api, fields, models
from odoo.exceptions import UserError

SEMANAS_HISTORICO = 4


def arredondar_receitas(quantidade, rendimento):
    """Para baixo, em receitas inteiras (capacidade é teto: não dá para passar)."""
    if not rendimento:
        return quantidade
    return math.floor(quantidade / rendimento + 1e-9) * rendimento


class BotecoPlanoProducao(models.TransientModel):
    _name = "boteco.plano.producao"
    _description = "Plano de produção sugerido"

    data = fields.Date("Produzir para", default=fields.Date.context_today, required=True)
    warehouse_id = fields.Many2one("stock.warehouse", string="Cozinha", default=lambda s: s._armazem_padrao())
    linha_ids = fields.One2many("boteco.plano.producao.linha", "plano_id", string="Sugestões")
    alertas = fields.Text("Avisos", readonly=True)

    @api.model
    def _armazem_padrao(self):
        Armazem = self.env["stock.warehouse"]
        return (Armazem.search([("boteco_tipo_unidade", "=", "cozinha_central"), ("company_id", "=", self.env.company.id)], limit=1)
                or Armazem.search([("company_id", "=", self.env.company.id)], limit=1))

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

    @staticmethod
    def _em_kg(produto, quantidade, kg):
        if produto.uom_id.category_id == kg.category_id:
            return produto.uom_id._compute_quantity(quantidade, kg)
        return 0.0  # item contado em unidades não entra no limite em kg

    def action_calcular(self):
        self.ensure_one()
        company = self.env.company
        armazem = self.warehouse_id
        produtos = self.env["product.product"].search([("boteco_produzido_cozinha", "=", True)])
        Bom = self.env["mrp.bom"]
        reservar = company.boteco_recurso_ativo("reserva_estoque_bar_b2b")
        dados = []
        for produto in produtos:
            bom = Bom._bom_find(produto, bom_type="normal").get(produto)
            dias = produto.boteco_dias_cobertura or 2
            media = self._saida_media_dia_semana(produto, self.data)
            b2b = self._pedidos_b2b_abertos(produto, self.data + timedelta(days=dias))
            reserva = produto.boteco_estoque_min_bar if reservar else 0.0
            estoque = produto.qty_available
            em_producao = sum(self.env["mrp.production"].search([
                ("product_id", "=", produto.id), ("state", "in", ("confirmed", "progress"))]).mapped("product_qty"))
            necessidade = media * dias + b2b + reserva - estoque - em_producao
            if bom and necessidade > 0:
                # Arredonda para receitas inteiras (ex.: receita rende 10 kg)
                lotes = -(-necessidade // (bom.product_qty or 1))
                sugerido = lotes * (bom.product_qty or 1)
            else:
                sugerido = max(necessidade, 0.0)
            dados.append({
                "product_id": produto.id, "bom_id": bom.id if bom else False,
                "media_saida": media, "dias_cobertura": dias, "pedidos_b2b": b2b, "reserva_bar": reserva,
                "estoque": estoque, "em_producao": em_producao, "necessidade": max(necessidade, 0.0),
                "quantidade": sugerido, "limitado_por": False, "_produto": produto, "_bom": bom,
                # Prioridade: compromisso B2B primeiro, depois quem tem menos dias de estoque
                "_prioridade": (0 if b2b > 0 else 1, (estoque / media) if media else 0.0),
            })
        self._nivelar(dados, armazem)
        alertas = self._insumos_faltantes(dados, armazem) if company.boteco_recurso_ativo("explosao_insumos_fator_coccao") else []
        self.linha_ids = [fields.Command.clear()] + [
            fields.Command.create({k: v for k, v in d.items() if not k.startswith("_")}) for d in dados
        ]
        self.alertas = "\n".join(alertas) or False
        return {"type": "ir.actions.act_window", "res_model": self._name, "res_id": self.id, "view_mode": "form",
                "target": "new"}

    # ------------------------------------------------------------------
    # Capacidade finita (item, cozinha e freezer)
    # ------------------------------------------------------------------
    def _nivelar(self, dados, armazem):
        company = self.env.company
        kg = self.env.ref("uom.product_uom_kgm")
        por_capacidade = company.boteco_recurso_ativo("capacidade_finita_congelados")
        por_freezer = company.boteco_recurso_ativo("controle_volume_freezer")
        sobra_kg = armazem.boteco_capacidade_prod_diaria_kg if (por_capacidade and armazem) else 0.0
        limitar_kg = bool(sobra_kg)
        livre_l = None
        if por_freezer and armazem and armazem.boteco_capacidade_freezer_litros:
            livre_l = max(armazem.boteco_capacidade_freezer_litros - armazem._boteco_ocupacao_freezer(), 0.0)
        for d in sorted(dados, key=lambda x: x["_prioridade"]):
            produto, bom = d["_produto"], d["_bom"]
            rendimento = bom.product_qty if bom else 0.0
            qtd = d["quantidade"]
            if qtd <= 0:
                continue
            motivos = []
            if por_capacidade and produto.boteco_lote_max_diario and qtd > produto.boteco_lote_max_diario:
                qtd = arredondar_receitas(produto.boteco_lote_max_diario, rendimento)
                motivos.append(_("máximo do item por dia"))
            if limitar_kg:
                peso = self._em_kg(produto, qtd, kg)
                if peso > sobra_kg:
                    fator = sobra_kg / peso if peso else 0.0
                    qtd = arredondar_receitas(qtd * fator, rendimento)
                    motivos.append(_("capacidade da cozinha"))
                sobra_kg = max(sobra_kg - self._em_kg(produto, qtd, kg), 0.0)
            volume = produto.boteco_volume_freezer_litros
            if livre_l is not None and volume:
                if qtd * volume > livre_l:
                    qtd = arredondar_receitas(livre_l / volume, rendimento)
                    motivos.append(_("espaço no freezer"))
                livre_l = max(livre_l - qtd * volume, 0.0)
            d["quantidade"] = max(qtd, 0.0)
            d["limitado_por"] = ", ".join(motivos) or False

    # ------------------------------------------------------------------
    # Explosão de insumos
    # ------------------------------------------------------------------
    def _insumos_faltantes(self, dados, armazem):
        """Soma o que todas as produções sugeridas consomem e compara com o estoque da cozinha."""
        precisa = {}
        usados = {}
        for i, d in enumerate(dados):
            bom = d["_bom"]
            if not bom or d["quantidade"] <= 0:
                continue
            _boms, linhas = bom.explode(d["_produto"], d["quantidade"] / (bom.product_qty or 1.0))
            for linha, info in linhas:
                componente = linha.product_id
                qtd = linha.product_uom_id._compute_quantity(info["qty"], componente.uom_id)
                precisa[componente] = precisa.get(componente, 0.0) + qtd
                usados.setdefault(i, set()).add(componente)
        alertas = []
        faltando = set()
        for componente, qtd in precisa.items():
            em_estoque = componente.with_context(warehouse_id=armazem.id).qty_available if armazem else componente.qty_available
            if em_estoque + 1e-6 < qtd:
                faltando.add(componente)
                alertas.append(_("Falta %(item)s: precisa %(p).2f %(u)s, tem %(t).2f",
                                 item=componente.display_name, p=qtd, u=componente.uom_id.name, t=em_estoque))
        for i, d in enumerate(dados):
            nomes = sorted(c.display_name for c in usados.get(i, set()) & faltando)
            d["insumos_faltando"] = ", ".join(nomes) or False
        return alertas

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
    reserva_bar = fields.Float("Reserva do bar")
    estoque = fields.Float("Em estoque")
    em_producao = fields.Float("Em produção")
    necessidade = fields.Float("Necessidade")
    quantidade = fields.Float("Produzir")
    limitado_por = fields.Char("Limitado por")
    insumos_faltando = fields.Char("Insumos faltando")
