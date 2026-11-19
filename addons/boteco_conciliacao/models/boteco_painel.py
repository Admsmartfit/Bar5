from datetime import timedelta

from odoo import api, fields, models


class BotecoPainel(models.AbstractModel):
    _inherit = "boteco.painel"

    @api.model
    def dados(self):
        resultado = super().dados()
        company = self.env.company
        if not company.boteco_recurso_ativo("conciliacao_cartoes"):
            return resultado  # flag desligada: o card some
        hoje = fields.Date.context_today(self)
        Recebivel = self.env["boteco.recebivel"].sudo()
        base = [("company_id", "=", company.id)]
        a_receber = Recebivel.search(base + [("estado", "in", ("previsto", "conferido", "divergente", "atrasado")),
                                             ("data_prevista", "<=", hoje + timedelta(days=30))])
        # Mesmo calendário da DRE: dia de operação (venda das 2h do dia 1º é do mês anterior)
        hoje_operacao = company.boteco_dia_operacao()
        semana = Recebivel.search(base + [("estado", "in", ("divergente", "atrasado", "estornado")),
                                          ("dia_operacao", ">=", hoje_operacao - timedelta(days=7))])
        mes = Recebivel.search(base + [("dia_operacao", ">=", hoje_operacao.replace(day=1)), ("estado", "!=", "estornado")])
        taxas = {}
        for r in mes:
            nome = r.adquirente_id.name or r.metodo_id.name or "—"
            taxa = r.taxa_cobrada if r.extrato_linha_id else r.valor_bruto - r.liquido_esperado
            taxas[nome] = taxas.get(nome, 0.0) + taxa
        conferir = self.env["boteco.extrato.linha"].sudo().search_count(
            [("company_id", "=", company.id), ("estado", "=", "conferir")])
        resultado["cartoes"] = {
            "a_receber_30": round(sum(r._liquido_real() for r in a_receber), 2),
            "diferencas_semana": {"quantidade": len(semana),
                                  "valor": round(sum(semana.mapped("valor_perdido")) +
                                                 sum(semana.filtered(lambda r: r.estado != "divergente").mapped("valor_bruto")), 2)},
            "atrasados": len(a_receber.filtered(lambda r: r.estado == "atrasado")),
            "taxa_mes": sorted([{"nome": n, "valor": round(v, 2)} for n, v in taxas.items()], key=lambda t: -t["valor"]),
            "conferir": conferir,
        }
        return resultado
