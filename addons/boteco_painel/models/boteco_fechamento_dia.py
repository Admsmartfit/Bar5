"""Fechamento do dia ("redução Z"): tudo o que o dono confere no fim da noite."""

import base64
import io
from collections import defaultdict

import xlsxwriter

from odoo import _, api, fields, models

ESTADOS_PAGOS = ("paid", "done", "invoiced")


class BotecoFechamentoDia(models.TransientModel):
    _name = "boteco.fechamento.dia"
    _description = "Fechamento do dia (redução Z)"

    dia = fields.Date("Dia de operação", required=True,
                      default=lambda s: s.env.company.boteco_dia_operacao(fields.Datetime.now()))
    company_id = fields.Many2one("res.company", default=lambda s: s.env.company, required=True)
    arquivo = fields.Binary(readonly=True)
    nome_arquivo = fields.Char()

    @api.model
    def calcular(self, dia, company=None):
        company = company or self.env.company
        inicio, fim = company.boteco_intervalo_dia(dia)
        Pedido = self.env["pos.order"].sudo()
        pedidos = Pedido.search([("boteco_dia_operacao", "=", dia), ("company_id", "=", company.id),
                                 ("state", "in", ESTADOS_PAGOS)])
        normais = pedidos.filtered(lambda p: p.boteco_tipo_conta != "funcionario")
        funcionarios = pedidos - normais
        vendas = sum(normais.mapped("amount_total"))
        clientes = sum(max(p.customer_count or 0, 1 if p.table_id else 0) for p in normais)

        por_forma = defaultdict(lambda: {"valor": 0.0, "quantidade": 0})
        for pagamento in pedidos.payment_ids:
            item = por_forma[pagamento.payment_method_id.name]
            item["valor"] += pagamento.amount
            if not pagamento.is_change:
                item["quantidade"] += 1

        Auditoria = self.env["boteco.auditoria"].sudo()
        dominio_dia = [("data", ">=", inicio), ("data", "<", fim), ("company_id", "=", company.id)]
        cancelamentos = Auditoria.search(dominio_dia + [("acao", "=", "cancelar_item")])
        sangrias = Auditoria.search(dominio_dia + [("acao", "=", "sangria")])
        reforcos = Auditoria.search(dominio_dia + [("acao", "=", "reforco")])

        fechamentos = self.env["boteco.fechamento.caixa"].sudo().search(
            [("dia_operacao", "=", dia), ("company_id", "=", company.id)])
        caixa = {
            "esperado": sum(fechamentos.mapped("total_esperado")),
            "contado": sum(fechamentos.mapped("total_contado")),
            "diferenca": sum(fechamentos.mapped("diferenca")),
            "linhas": [{"forma": l.nome, "esperado": l.esperado, "contado": l.contado, "diferenca": l.diferenca}
                       for l in fechamentos.linha_ids],
        }
        aberturas = sum(fechamentos.session_id.mapped("cash_register_balance_start"))
        movimentos = sum(fechamentos.session_id.sudo().statement_line_ids.mapped("amount"))
        # Conferência: o esperado dos caixas = vendas do dia + troco inicial + sangrias/reforços
        conferencia = round(caixa["esperado"] - aberturas - movimentos, 2) if fechamentos else None

        return {
            "dia": fields.Date.to_string(dia),
            "empresa": company.name,
            "contas": len(normais),
            "clientes": clientes,
            "vendas": vendas,
            "ticket_medio": round(vendas / clientes, 2) if clientes else 0.0,
            "taxa_servico": sum(normais.mapped("boteco_taxa_servico")),
            "couvert": sum(normais.mapped("boteco_couvert")),
            "descontos": sum(pedidos.mapped("boteco_total_desconto")),
            "cortesias": sum(pedidos.mapped("boteco_total_cortesia")),
            "consumo_funcionarios": {"contas": len(funcionarios), "valor": sum(funcionarios.mapped("amount_total"))},
            "formas_pagamento": [{"forma": k, **v} for k, v in sorted(por_forma.items())],
            "total_pagamentos": round(sum(v["valor"] for v in por_forma.values()), 2),
            "cancelamentos": {"quantidade": len(cancelamentos), "valor": sum(cancelamentos.mapped("valor")),
                              "itens": [{"descricao": c.descricao, "motivo": c.motivo or "", "valor": c.valor,
                                         "autorizado_por": c.autorizado_por_id.name or ""} for c in cancelamentos]},
            "sangrias": sum(sangrias.mapped("valor")),
            "reforcos": sum(reforcos.mapped("valor")),
            "caixa": caixa,
            "conferencia_vendas_caixa": conferencia,
        }

    def action_imprimir(self):
        self.ensure_one()
        return self.env.ref("boteco_painel.report_fechamento_dia").report_action(self)

    def action_excel(self):
        self.ensure_one()
        dados = self.calcular(self.dia, self.company_id)
        saida = io.BytesIO()
        livro = xlsxwriter.Workbook(saida, {"in_memory": True})
        aba = livro.add_worksheet(_("Fechamento"))
        negrito = livro.add_format({"bold": True})
        dinheiro = livro.add_format({"num_format": "R$ #,##0.00"})
        linhas = [
            (_("Dia"), dados["dia"]), (_("Contas"), dados["contas"]), (_("Clientes"), dados["clientes"]),
            (_("Vendas"), dados["vendas"]), (_("Ticket médio"), dados["ticket_medio"]),
            (_("Taxa de serviço"), dados["taxa_servico"]), (_("Couvert"), dados["couvert"]),
            (_("Descontos"), dados["descontos"]), (_("Cortesias"), dados["cortesias"]),
            (_("Cancelamentos (R$)"), dados["cancelamentos"]["valor"]),
            (_("Sangrias"), dados["sangrias"]), (_("Reforços"), dados["reforcos"]),
            (_("Diferença de caixa"), dados["caixa"]["diferenca"]),
        ]
        for i, (rotulo, valor) in enumerate(linhas):
            aba.write(i, 0, rotulo, negrito)
            if isinstance(valor, float):
                aba.write_number(i, 1, valor, dinheiro)
            else:
                aba.write(i, 1, valor)
        linha = len(linhas) + 1
        aba.write(linha, 0, _("Forma de pagamento"), negrito)
        aba.write(linha, 1, _("Valor"), negrito)
        for forma in dados["formas_pagamento"]:
            linha += 1
            aba.write(linha, 0, forma["forma"])
            aba.write_number(linha, 1, forma["valor"], dinheiro)
        aba.set_column(0, 0, 28)
        aba.set_column(1, 1, 16)
        livro.close()
        self.write({"arquivo": base64.b64encode(saida.getvalue()), "nome_arquivo": "fechamento-%s.xlsx" % dados["dia"]})
        return {"type": "ir.actions.act_url", "target": "self",
                "url": "/web/content/%s/%s/arquivo/%s?download=true" % (self._name, self.id, self.nome_arquivo)}
