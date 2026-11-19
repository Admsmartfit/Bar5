"""Conferência de cartões e Pix (Etapa 28): o dinheiro de cada venda chegou, no valor e no prazo combinados?"""

from datetime import timedelta

import pytz

from odoo import _, api, fields, models

MODALIDADES = [("debito", "Débito"), ("credito", "Crédito à vista"), ("parcelado", "Crédito parcelado"), ("pix", "Pix")]
TOLERANCIA_TAXA_PP = 0.05  # diferença de taxa (pontos percentuais) que não vira alerta: arredondamento


def dia_util(dia, dias):
    """Soma dias corridos e empurra sábado/domingo para segunda (repasse não cai no fim de semana)."""
    dia = dia + timedelta(days=dias)
    while dia.weekday() >= 5:
        dia += timedelta(days=1)
    return dia


def proximo_dia_util(dia):
    dia += timedelta(days=1)
    while dia.weekday() >= 5:
        dia += timedelta(days=1)
    return dia


class BotecoAdquirente(models.Model):
    _name = "boteco.adquirente"
    _description = "Maquininha / adquirente"
    _order = "name"

    name = fields.Char("Nome", required=True, help="Stone, Cielo, Rede, PagSeguro, Mercado Pago, banco do Pix…")
    metodo_ids = fields.One2many("pos.payment.method", "boteco_adquirente_id", string="Formas de pagamento do caixa")
    taxa_ids = fields.One2many("boteco.adquirente.taxa", "adquirente_id", string="Taxas contratadas")
    # Leitor do extrato: em branco = o sistema reconhece o cabeçalho sozinho (nomes mais comuns das maquininhas)
    coluna_data = fields.Char("Coluna: data da venda")
    coluna_bruto = fields.Char("Coluna: valor bruto")
    coluna_liquido = fields.Char("Coluna: valor líquido")
    coluna_taxa = fields.Char("Coluna: taxa (R$)")
    coluna_nsu = fields.Char("Coluna: NSU / código")
    coluna_bandeira = fields.Char("Coluna: bandeira")
    coluna_modalidade = fields.Char("Coluna: produto / modalidade")
    coluna_parcelas = fields.Char("Coluna: parcelas")
    coluna_previsao = fields.Char("Coluna: previsão de pagamento")
    active = fields.Boolean(default=True)
    company_id = fields.Many2one("res.company", required=True, default=lambda s: s.env.company)

    def _taxa(self, modalidade, parcelas=1):
        """(taxa %, prazo em dias) contratados para a modalidade."""
        self.ensure_one()
        for t in self.taxa_ids.sorted("parcelas_de"):
            if t.modalidade == modalidade and t.parcelas_de <= (parcelas or 1) <= (t.parcelas_ate or 99):
                return t.taxa_pct, t.prazo_dias
        return None


class BotecoAdquirenteTaxa(models.Model):
    _name = "boteco.adquirente.taxa"
    _description = "Taxa contratada com a maquininha"
    _order = "modalidade, parcelas_de"

    adquirente_id = fields.Many2one("boteco.adquirente", required=True, ondelete="cascade")
    modalidade = fields.Selection(MODALIDADES, required=True, default="debito")
    parcelas_de = fields.Integer("Parcelas de", default=1)
    parcelas_ate = fields.Integer("até", default=1)
    taxa_pct = fields.Float("Taxa (%)", digits=(5, 2))
    prazo_dias = fields.Integer("Cai na conta em (dias)", default=1, help="D+1 = 1; crédito costuma ser 30.")


class PosPaymentMethod(models.Model):
    _inherit = "pos.payment.method"

    boteco_adquirente_id = fields.Many2one("boteco.adquirente", string="Maquininha / banco")
    boteco_modalidade = fields.Selection(MODALIDADES, string="Modalidade")


class BotecoRecebivel(models.Model):
    _name = "boteco.recebivel"
    _description = "Recebível de cartão / Pix"
    _order = "data_venda desc, id desc"

    payment_id = fields.Many2one("pos.payment", string="Pagamento no caixa", ondelete="set null", index=True)
    order_id = fields.Many2one(related="payment_id.pos_order_id", store=True, string="Conta")
    session_id = fields.Many2one("pos.session", string="Caixa", index=True)
    metodo_id = fields.Many2one("pos.payment.method", string="Forma de pagamento")
    adquirente_id = fields.Many2one("boteco.adquirente", string="Maquininha / banco", index=True)
    modalidade = fields.Selection(MODALIDADES)
    parcelas = fields.Integer(default=1)
    data_venda = fields.Date("Venda", required=True, index=True,
                             help="Data do calendário: é a que a maquininha usa no extrato.")
    dia_operacao = fields.Date("Dia de operação", index=True,
                               help="Dia do bar (vira na hora configurada): é o usado no Painel e na DRE.")
    data_prevista = fields.Date("Cai na conta em", index=True)
    valor_bruto = fields.Monetary("Venda", currency_field="currency_id")
    taxa_esperada_pct = fields.Float("Taxa contratada (%)", digits=(5, 2))
    liquido_esperado = fields.Monetary("Líquido esperado", currency_field="currency_id")
    taxa_cobrada = fields.Monetary("Taxa cobrada", currency_field="currency_id")
    taxa_cobrada_pct = fields.Float("Taxa cobrada (%)", digits=(5, 2))
    valor_perdido = fields.Monetary("Pago a mais", currency_field="currency_id")
    nsu = fields.Char("NSU")
    estado = fields.Selection([
        ("previsto", "Previsto"), ("conferido", "Conferido na maquininha"), ("pago", "Caiu na conta"),
        ("divergente", "Diferença"), ("atrasado", "Atrasado"), ("estornado", "Estornado"),
    ], default="previsto", required=True, index=True)
    alerta = fields.Char("Alerta")
    extrato_linha_id = fields.Many2one("boteco.extrato.linha", string="Linha do extrato", ondelete="set null")
    currency_id = fields.Many2one(related="company_id.currency_id")
    company_id = fields.Many2one("res.company", required=True, default=lambda s: s.env.company, index=True)

    @api.model
    def _boteco_de_pagamentos(self, pagamentos):
        """Cada pagamento de cartão/Pix do caixa vira um recebível previsto (só com a conferência ligada)."""
        vals = []
        for pag in pagamentos:
            metodo = pag.payment_method_id
            company = pag.company_id or pag.pos_order_id.company_id
            if (pag.amount <= 0 or metodo.is_cash_count or not metodo.boteco_modalidade
                    or not company.boteco_recurso_ativo("conciliacao_cartoes")):
                continue
            modalidade = metodo.boteco_modalidade
            contratado = metodo.boteco_adquirente_id._taxa(modalidade) if metodo.boteco_adquirente_id else None
            taxa, prazo = contratado or (metodo.boteco_taxa_pct or 0.0, metodo.boteco_dias_recebimento or 0)
            tz = pytz.timezone(company.partner_id.tz or "America/Sao_Paulo")
            dia = pytz.utc.localize(pag.payment_date).astimezone(tz).date()
            vals.append({
                "payment_id": pag.id, "session_id": pag.session_id.id, "metodo_id": metodo.id,
                "adquirente_id": metodo.boteco_adquirente_id.id, "modalidade": modalidade,
                "data_venda": dia, "data_prevista": dia_util(dia, prazo) if prazo else dia,
                "dia_operacao": company.boteco_dia_operacao(pag.payment_date),
                "valor_bruto": pag.amount, "taxa_esperada_pct": taxa,
                "liquido_esperado": round(pag.amount * (1 - taxa / 100.0), 2),
                "nsu": pag.transaction_id or pag.payment_ref_no or False, "company_id": company.id,
            })
        return self.sudo().create(vals) if vals else self.browse()

    def _liquido_real(self):
        self.ensure_one()
        return self.valor_bruto - self.taxa_cobrada if self.extrato_linha_id else self.liquido_esperado

    @api.model
    def _cron_atrasados(self):
        """Repasse que não caiu até a data prevista + 1 dia útil vira 'atrasado'."""
        hoje = fields.Date.context_today(self)
        for r in self.sudo().search([("estado", "in", ("previsto", "conferido", "divergente")),
                                     ("data_prevista", "<", hoje)]):
            if not r.company_id.boteco_recurso_ativo("conciliacao_cartoes"):
                continue
            if proximo_dia_util(r.data_prevista) < hoje:
                r.write({"estado": "atrasado",
                         "alerta": _("Repasse previsto para %s não caiu na conta.", r.data_prevista.strftime("%d/%m"))})
        return True


class PosPayment(models.Model):
    _inherit = "pos.payment"

    @api.model_create_multi
    def create(self, vals_list):
        pagamentos = super().create(vals_list)
        self.env["boteco.recebivel"]._boteco_de_pagamentos(pagamentos)
        return pagamentos


class PosSession(models.Model):
    _inherit = "pos.session"

    boteco_cartoes_total = fields.Monetary("Cartões e Pix do caixa", compute="_compute_boteco_conferencia",
                                           currency_field="currency_id")
    boteco_cartoes_confirmado = fields.Monetary("Já confirmado pela maquininha/banco",
                                                compute="_compute_boteco_conferencia", currency_field="currency_id")

    def _compute_boteco_conferencia(self):
        Recebivel = self.env["boteco.recebivel"].sudo()
        for sessao in self:
            recebiveis = Recebivel.search([("session_id", "=", sessao.id)])
            sessao.boteco_cartoes_total = sum(recebiveis.mapped("valor_bruto"))
            sessao.boteco_cartoes_confirmado = sum(
                recebiveis.filtered(lambda r: r.estado in ("conferido", "pago")).mapped("valor_bruto"))
