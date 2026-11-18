"""Números do painel do dono (a noite em tempo real e o mês)."""

from datetime import timedelta

from odoo import api, fields, models


class BotecoPainel(models.AbstractModel):
    _name = "boteco.painel"
    _description = "Painel do dono"

    @api.model
    def _noite(self, dia, company):
        """Números de uma noite (inclui contas ainda abertas: é o 'em tempo real')."""
        Pedido = self.env["pos.order"].sudo()
        pedidos = Pedido.search([("boteco_dia_operacao", "=", dia), ("company_id", "=", company.id),
                                 ("state", "in", ("draft", "paid", "done", "invoiced")),
                                 ("boteco_tipo_conta", "!=", "funcionario")])
        pagos = pedidos.filtered(lambda p: p.state != "draft")
        faturamento = sum(pedidos.mapped("amount_total"))
        clientes = sum(max(p.customer_count or 0, 1 if p.table_id else 0) for p in pedidos)
        return {
            "faturamento": round(faturamento, 2),
            "faturamento_pago": round(sum(pagos.mapped("amount_total")), 2),
            "contas_abertas": len(pedidos - pagos),
            "clientes": clientes,
            "ticket_medio": round(faturamento / clientes, 2) if clientes else 0.0,
            "cortesias": round(sum(pedidos.mapped("boteco_total_cortesia")), 2),
        }

    @api.model
    def dados(self):
        company = self.env.company
        agora = fields.Datetime.now()
        hoje = company.boteco_dia_operacao(agora)
        semana_passada = hoje - timedelta(days=7)
        inicio, fim = company.boteco_intervalo_dia(hoje)
        noite = self._noite(hoje, company)
        anterior = self._noite(semana_passada, company)

        # Itens mais vendidos da noite
        linhas = self.env["pos.order.line"].sudo().search([
            ("order_id.boteco_dia_operacao", "=", hoje), ("order_id.company_id", "=", company.id),
            ("order_id.state", "in", ("draft", "paid", "done", "invoiced")), ("qty", ">", 0),
            ("product_id.type", "!=", "service"),
        ])
        ranking = {}
        for linha in linhas:
            item = ranking.setdefault(linha.product_id.id, {"nome": linha.product_id.name, "quantidade": 0.0, "valor": 0.0})
            item["quantidade"] += linha.qty
            item["valor"] += linha.price_subtotal_incl
        mais_vendidos = sorted(ranking.values(), key=lambda i: -i["quantidade"])[:8]

        # Tempo médio de entrega (KDS)
        tickets = self.env["boteco.kds.pedido"].sudo().search([
            ("company_id", "=", company.id), ("tipo", "=", "novo"), ("criado_em", ">=", inicio), ("criado_em", "<", fim)])
        prontos = tickets.filtered("pronto_em")
        tempo_medio = round(sum(prontos.mapped("minutos_preparo")) / len(prontos), 1) if prontos else 0.0
        atrasados = len(tickets.filtered(lambda t: t.estado in ("aguardando", "preparando")
                                         and (agora - t.criado_em).total_seconds() > 30 * 60))

        auditoria = self.env["boteco.auditoria"].sudo().search([
            ("company_id", "=", company.id), ("data", ">=", inicio), ("data", "<", fim),
            ("acao", "in", ("cancelar_item", "desconto", "cortesia"))])
        cancel = auditoria.filtered(lambda a: a.acao == "cancelar_item")

        cmv = self.env["boteco.cmv"].sudo().resumo_dia(hoje, company)

        # Metas do plano
        mes_inicio = hoje.replace(day=1)
        kg = self.env.ref("uom.product_uom_kgm")
        vendas_b2b = self.env["sale.order.line"].sudo().search([
            ("order_id.state", "=", "sale"), ("order_id.company_id", "=", company.id),
            ("order_id.date_order", ">=", fields.Datetime.to_datetime(mes_inicio)),
            ("order_id.partner_id.commercial_partner_id.boteco_cliente_b2b", "=", True),
        ])
        kg_mes = sum(l.product_uom._compute_quantity(l.product_uom_qty, kg)
                     for l in vendas_b2b if l.product_uom.category_id == kg.category_id)
        bares = self.env["boteco.contrato.assessoria"].sudo().search_count(
            [("estado", "=", "ativo"), ("company_id", "=", company.id)])

        # Contas vencidas
        Fatura = self.env["account.move"].sudo()
        dominio_vencidas = [("company_id", "=", company.id), ("state", "=", "posted"),
                            ("payment_state", "in", ("not_paid", "partial")), ("invoice_date_due", "<", fields.Date.today())]
        receber = Fatura.search(dominio_vencidas + [("move_type", "=", "out_invoice")])
        pagar = Fatura.search(dominio_vencidas + [("move_type", "=", "in_invoice")])

        def variacao(atual, antes):
            return round((atual - antes) * 100.0 / antes, 1) if antes else None

        alertas = self._alertas_extras(company)

        return {
            "dia": hoje.strftime("%d/%m/%Y"),
            "atualizado": fields.Datetime.to_string(agora),
            "noite": noite,
            "semana_passada": anterior,
            "variacao_faturamento": variacao(noite["faturamento"], anterior["faturamento"]),
            "variacao_clientes": variacao(noite["clientes"], anterior["clientes"]),
            "cmv_pct": cmv["cmv_pct"],
            "mais_vendidos": mais_vendidos,
            "tempo_medio_entrega": tempo_medio,
            "pedidos_atrasados": atrasados,
            "cancelamentos": {"quantidade": len(cancel), "valor": round(sum(cancel.mapped("valor")), 2)},
            "descontos_cortesias": round(sum((auditoria - cancel).mapped("valor")), 2),
            "metas": [
                {"nome": "Clientes por noite", "valor": noite["clientes"], "meta": company.boteco_meta_clientes_noite,
                 "unidade": ""},
                {"nome": "Kg vendidos a bares no mês", "valor": round(kg_mes, 1), "meta": company.boteco_meta_kg_b2b_mes,
                 "unidade": "kg"},
                {"nome": "Bares com assessoria", "valor": bares, "meta": company.boteco_meta_bares_assessoria, "unidade": ""},
            ],
            "receber_vencido": {"quantidade": len(receber), "valor": round(sum(receber.mapped("amount_residual")), 2)},
            "pagar_vencido": {"quantidade": len(pagar), "valor": round(sum(pagar.mapped("amount_residual")), 2)},
            "alertas": alertas,
            "oportunidades_compra": self._oportunidades_compra(company),
        }

    @api.model
    def _oportunidades_compra(self, company):
        """Etapa 18: insumos com preço interessante e quanto economizam nas receitas de congelados."""
        if not company.boteco_recurso_ativo("radar_precos_oportunidade"):
            return []
        cozinha = self.env["stock.warehouse"].sudo().search(
            [("company_id", "=", company.id), ("boteco_tipo_unidade", "=", "cozinha_central")],
            order="boteco_capacidade_freezer_litros desc, id", limit=1)
        livre = cozinha.boteco_freezer_livre_litros if cozinha and cozinha.boteco_capacidade_freezer_litros else None
        resultado = []
        for cotacao in self.env["boteco.historico.preco"].sudo().with_company(company).oportunidades():
            insumo = cotacao.product_id
            linhas = self.env["mrp.bom.line"].sudo().search([
                ("product_id", "=", insumo.id), ("bom_id.active", "=", True),
                ("bom_id.product_tmpl_id.boteco_produzido_cozinha", "=", True),
            ])
            receitas = []
            for linha in linhas:
                qtd = linha.product_uom_id._compute_quantity(linha.product_qty, insumo.uom_id)
                receitas.append({
                    "produto": linha.bom_id.product_tmpl_id.name,
                    "economia_receita": round((cotacao.media_60d - cotacao.preco_unitario) * qtd, 2),
                })
            resultado.append({
                "insumo": insumo.display_name,
                "fornecedor": cotacao.partner_id.name or "",
                "preco": cotacao.preco_unitario,
                "media": round(cotacao.media_60d, 2),
                "queda_pct": round(-cotacao.variacao_pct, 1),
                "origem": dict(cotacao._fields["origem"].selection).get(cotacao.origem, ""),
                "receitas": receitas,
                "economia_total_receita": round(sum(r["economia_receita"] for r in receitas), 2),
                "freezer_livre_litros": round(livre, 1) if livre is not None else None,
            })
        return sorted(resultado, key=lambda r: -r["economia_total_receita"])[:8]

    @api.model
    def _alertas_extras(self, company):
        """Ponto de extensão (ex.: boteco_fiscal_export avisa notas pendentes há muitos dias)."""
        return []

    @api.model
    def fluxo_caixa(self, dias=30):
        """Previsto (a receber e a pagar em aberto, por semana) x realizado (pagamentos feitos)."""
        company = self.env.company
        hoje = fields.Date.context_today(self)
        Fatura = self.env["account.move"].sudo()
        abertas = Fatura.search([("company_id", "=", company.id), ("state", "=", "posted"),
                                 ("payment_state", "in", ("not_paid", "partial")),
                                 ("move_type", "in", ("out_invoice", "in_invoice")),
                                 ("invoice_date_due", "<=", hoje + timedelta(days=dias))])
        semanas = {}
        for fatura in abertas:
            semana = max(fatura.invoice_date_due, hoje)
            chave = (semana - timedelta(days=semana.weekday())).isoformat()
            item = semanas.setdefault(chave, {"semana": chave, "entrar": 0.0, "sair": 0.0})
            if fatura.move_type == "out_invoice":
                item["entrar"] += fatura.amount_residual
            else:
                item["sair"] += fatura.amount_residual
        pagos = self.env["account.payment"].sudo().search([
            ("company_id", "=", company.id), ("state", "in", ("paid", "in_process")),
            ("date", ">=", hoje - timedelta(days=dias))])
        return {
            "previsto": sorted(semanas.values(), key=lambda s: s["semana"]),
            "realizado": {
                "recebido": round(sum(pagos.filtered(lambda p: p.payment_type == "inbound").mapped("amount")), 2),
                "pago": round(sum(pagos.filtered(lambda p: p.payment_type == "outbound").mapped("amount")), 2),
            },
        }
