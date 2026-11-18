from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class MrpBom(models.Model):
    """Receita de produção da cozinha central (lista de materiais do tipo 'fabricar')."""

    _inherit = "mrp.bom"

    boteco_perda_esperada = fields.Float(
        "Perda esperada (%)", help="Quanto se perde no preparo (limpeza, cocção). Só informativo para comparar com o real.")
    boteco_modo_preparo = fields.Html("Modo de preparo")
    boteco_tempo_preparo_min = fields.Integer("Tempo de preparo (min)")
    # Etapa 17: fator de cocção (peso depois do fogo / peso antes). Ex.: carne perde 30% -> 0,70
    boteco_fator_coccao = fields.Float(
        "Fator de cocção", default=1.0, digits=(16, 3),
        help="Peso pronto ÷ peso cru. 1,00 = não muda no preparo; 0,70 = perde 30% no fogo.")
    boteco_rendimento_estimado = fields.Float(
        "Rendimento estimado", compute="_compute_boteco_rendimento", digits=(16, 3),
        help="Soma dos insumos limpos x fator de cocção. Compare com a quantidade que a receita produz.")

    @api.depends("bom_line_ids.boteco_qtd_liquida", "bom_line_ids.product_qty",
                 "bom_line_ids.boteco_fator_correcao", "boteco_fator_coccao")
    def _compute_boteco_rendimento(self):
        for bom in self:
            limpo = sum(
                (l.boteco_qtd_liquida or (l.product_qty / (l.boteco_fator_correcao or 1.0))) for l in bom.bom_line_ids
            )
            bom.boteco_rendimento_estimado = limpo * (bom.boteco_fator_coccao or 1.0)

    @api.constrains("boteco_fator_coccao")
    def _check_boteco_fator_coccao(self):
        for bom in self:
            if bom.boteco_fator_coccao <= 0:
                raise ValidationError(_("O fator de cocção precisa ser maior que zero."))

    @api.model_create_multi
    def create(self, vals_list):
        # Na cozinha o peso final varia: consumo flexível evita o aviso "consumiu diferente do previsto"
        for vals in vals_list:
            vals.setdefault("consumption", "flexible")
        return super().create(vals_list)


class MrpBomLine(models.Model):
    _inherit = "mrp.bom.line"

    # Etapa 17: fator de correção (peso bruto ÷ peso limpo). Ex.: cebola com casca 1,10
    boteco_fator_correcao = fields.Float(
        "Fator de correção", default=1.0, digits=(16, 3),
        help="Peso bruto comprado ÷ peso limpo usado. 1,00 = sem perda na limpeza/descasque.")
    boteco_qtd_liquida = fields.Float(
        "Qtd. limpa", digits="Product Unit of Measure",
        help="Quanto a receita usa depois de limpo. Preenchido, a quantidade consumida do estoque "
        "vira qtd. limpa x fator de correção (se o recurso estiver ligado na Central de Recursos).")

    @api.constrains("boteco_fator_correcao")
    def _check_boteco_fator_correcao(self):
        for linha in self:
            if linha.boteco_fator_correcao < 1.0:
                raise ValidationError(_("O fator de correção não pode ser menor que 1 (%s).", linha.product_id.display_name))

    @api.model_create_multi
    def create(self, vals_list):
        linhas = super().create(vals_list)
        linhas._boteco_recalcular_bruto()
        return linhas

    def write(self, vals):
        res = super().write(vals)
        if {"boteco_qtd_liquida", "boteco_fator_correcao"} & set(vals):
            self._boteco_recalcular_bruto()
        return res

    def _boteco_recalcular_bruto(self):
        if not self.env.company.boteco_recurso_ativo("explosao_insumos_fator_coccao"):
            return
        for linha in self.filtered("boteco_qtd_liquida"):
            bruto = linha.boteco_qtd_liquida * (linha.boteco_fator_correcao or 1.0)
            if linha.product_qty != bruto:
                super(MrpBomLine, linha).write({"product_qty": bruto})
