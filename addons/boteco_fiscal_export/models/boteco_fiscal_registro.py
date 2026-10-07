import re
from datetime import timedelta

from odoo import _, api, fields, models
from odoo.exceptions import UserError

ESTADOS = [("pendente", "Pendente"), ("exportado", "Exportado"), ("emitido", "Emitido"), ("nao_emitir", "Não emitir")]


def so_digitos(texto):
    return re.sub(r"\D", "", texto or "")


class BotecoFiscalRegistro(models.Model):
    """Registro fiscal de uma venda: tudo o que a nota precisa, para emitir depois em outro sistema."""

    _name = "boteco.fiscal.registro"
    _description = "Registro fiscal"
    _order = "data_venda desc, id desc"
    _rec_name = "referencia"

    tipo = fields.Selection([("nfce", "NFC-e (bar)"), ("nfe", "NF-e (venda a bares)")], required=True, index=True)
    estado = fields.Selection(ESTADOS, default="pendente", required=True, index=True)
    motivo_nao_emitir = fields.Char("Por que não emitir")
    origem_model = fields.Char("Origem (modelo)", required=True, readonly=True)
    origem_id = fields.Integer("Origem (id)", required=True, readonly=True, index=True)
    referencia = fields.Char("Venda", required=True, readonly=True, index=True)
    data_venda = fields.Datetime("Data e hora da venda", required=True, readonly=True, index=True)
    dia = fields.Date("Dia de operação", readonly=True, index=True)
    valor_total = fields.Monetary("Valor", readonly=True, currency_field="currency_id")
    taxa_servico = fields.Monetary("Taxa de serviço", readonly=True, currency_field="currency_id")
    cliente_documento = fields.Char("CPF/CNPJ do cliente", readonly=True)
    cliente_nome = fields.Char("Cliente", readonly=True)
    lote_ids = fields.Many2many("boteco.fiscal.lote", string="Lotes de exportação", readonly=True)
    numero_nota = fields.Char("Número da nota", readonly=True)
    chave_nota = fields.Char("Chave da nota", readonly=True, index=True)
    emitido_em = fields.Datetime("Emitida em", readonly=True)
    dias_pendente = fields.Integer(compute="_compute_dias_pendente")
    company_id = fields.Many2one("res.company", required=True, default=lambda s: s.env.company, index=True)
    currency_id = fields.Many2one(related="company_id.currency_id")

    _sql_constraints = [
        ("origem_unica", "unique(origem_model, origem_id, tipo)", "Esta venda já tem registro fiscal."),
    ]

    def _compute_dias_pendente(self):
        agora = fields.Datetime.now()
        for r in self:
            r.dias_pendente = (agora - r.data_venda).days if r.estado in ("pendente", "exportado") else 0

    def _origem(self):
        self.ensure_one()
        return self.env[self.origem_model].sudo().browse(self.origem_id).exists()

    # ------------------------------------------------------------------ dados da nota
    def _emitente(self):
        empresa = self.company_id
        parceiro = empresa.partner_id
        ie = getattr(empresa, "l10n_br_ie_code", False) or getattr(parceiro, "boteco_ie", False)
        return {
            "razao_social": empresa.name, "cnpj": so_digitos(empresa.vat), "ie": ie or "",
            "logradouro": parceiro.street or "", "numero": getattr(parceiro, "street_number", "") or "",
            "bairro": getattr(parceiro, "street2", "") or "", "municipio": parceiro.city or "",
            "uf": parceiro.state_id.code or "", "cep": so_digitos(parceiro.zip),
        }

    @staticmethod
    def _item(produto, quantidade, valor_unitario, desconto, unidade=None):
        tmpl = produto.product_tmpl_id
        return {
            "codigo": produto.default_code or str(produto.id),
            "descricao": produto.name,
            "ncm": so_digitos(tmpl.boteco_ncm),
            "cest": so_digitos(tmpl.boteco_cest),
            "cfop": so_digitos(tmpl.boteco_cfop),
            "cst_csosn": so_digitos(tmpl.boteco_cst_csosn),
            "origem": tmpl.boteco_origem or "0",
            "unidade": unidade or tmpl.boteco_unidade_fiscal or "UN",
            "quantidade": round(quantidade, 4),
            "valor_unitario": round(valor_unitario, 4),
            "desconto": round(desconto, 2),
            "valor_total": round(quantidade * valor_unitario - desconto, 2),
        }

    def _dados_pos(self, pedido):
        taxa_prod = pedido.config_id.boteco_produto_taxa_id
        itens = []
        for linha in pedido.lines.filtered(lambda l: l.qty > 0 and l.product_id != taxa_prod):
            bruto = linha.price_unit * linha.qty
            desconto = bruto * (linha.discount or 0.0) / 100.0
            if round(bruto - desconto, 2) <= 0:
                continue  # cortesia não entra na nota
            itens.append(self._item(linha.product_id, linha.qty, linha.price_unit, desconto))
        pagamentos = [{"forma": p.payment_method_id.name, "valor": round(p.amount, 2)}
                      for p in pedido.payment_ids if not p.is_change]
        troco = -sum(pedido.payment_ids.filtered("is_change").mapped("amount"))
        return itens, pagamentos, round(troco, 2)

    def _dados_entrega(self, entrega):
        itens = []
        for move in entrega.move_ids.filtered(lambda m: m.state == "done"):
            linha_venda = move.sale_line_id
            preco = linha_venda.price_unit if linha_venda else move.product_id.lst_price
            desconto = preco * move.quantity * (linha_venda.discount or 0.0) / 100.0 if linha_venda else 0.0
            itens.append(self._item(move.product_id, move.quantity, preco, desconto, unidade=move.product_uom.name.upper()[:6]))
        return itens, [{"forma": "a prazo", "valor": round(sum(i["valor_total"] for i in itens), 2)}], 0.0

    def dados_exportacao(self):
        """Dicionário completo de cada registro (base do CSV, Excel e JSON)."""
        resultado = []
        for r in self:
            origem = r._origem()
            if r.origem_model == "pos.order":
                itens, pagamentos, troco = r._dados_pos(origem)
            else:
                itens, pagamentos, troco = r._dados_entrega(origem)
            resultado.append({
                "registro_id": r.id,
                "tipo": r.tipo,
                "referencia": r.referencia,
                "data_hora": fields.Datetime.to_string(r.data_venda),
                "emitente": r._emitente(),
                "cliente_documento": r.cliente_documento or "",
                "cliente_nome": r.cliente_nome or "",
                "itens": itens,
                "taxa_servico": round(r.taxa_servico, 2),
                "pagamentos": pagamentos,
                "troco": troco,
                "valor_total": round(r.valor_total, 2),
            })
        return resultado

    def pendencias_cadastro(self):
        """Produtos sem NCM ou CFOP nos registros: bloqueiam a exportação."""
        faltando = {}
        for dados in self.dados_exportacao():
            for item in dados["itens"]:
                problemas = []
                if len(item["ncm"]) != 8:
                    problemas.append("NCM")
                if len(item["cfop"]) != 4:
                    problemas.append("CFOP")
                if problemas:
                    faltando.setdefault(item["descricao"], set()).update(problemas)
        return {produto: sorted(p) for produto, p in faltando.items()}

    # ------------------------------------------------------------------ ações
    def action_nao_emitir(self):
        motivo = self.env.context.get("motivo") or _("Marcado manualmente")
        for r in self.filtered(lambda x: x.estado in ("pendente", "exportado")):
            r.write({"estado": "nao_emitir", "motivo_nao_emitir": motivo})
            self.env["boteco.auditoria"].registrar("fiscal", registro=r, descricao=_("Não emitir: %s", r.referencia),
                                                   motivo=motivo)
        return True

    def action_voltar_pendente(self):
        self.filtered(lambda r: r.estado != "emitido").write({"estado": "pendente", "motivo_nao_emitir": False})
        return True

    def action_abrir_origem(self):
        self.ensure_one()
        return {"type": "ir.actions.act_window", "res_model": self.origem_model, "res_id": self.origem_id, "view_mode": "form"}

    def marcar_emitido(self, numero, chave):
        self.ensure_one()
        if self.estado == "nao_emitir":
            raise UserError(_("%s estava marcado para não emitir.", self.referencia))
        self.write({"estado": "emitido", "numero_nota": numero, "chave_nota": so_digitos(chave) or chave,
                    "emitido_em": fields.Datetime.now()})

    @api.model
    def pendentes_antigos(self, company=None):
        company = company or self.env.company
        dias = company.boteco_fiscal_dias_alerta or 3
        limite = fields.Datetime.now() - timedelta(days=dias)
        return self.search([("company_id", "=", company.id), ("estado", "in", ("pendente", "exportado")),
                            ("data_venda", "<", limite)])
