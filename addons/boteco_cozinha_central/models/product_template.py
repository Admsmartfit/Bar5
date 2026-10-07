from odoo import api, fields, models

CONSERVACOES = [
    ("congelado", "Congelado (-18 °C)"),
    ("resfriado", "Resfriado (0 a 5 °C)"),
    ("ambiente", "Temperatura ambiente"),
]
TEXTO_CONSERVACAO = {
    "congelado": "MANTER CONGELADO A -18 °C",
    "resfriado": "MANTER RESFRIADO DE 0 A 5 °C",
    "ambiente": "MANTER EM LOCAL SECO E AREJADO",
}


class ProductTemplate(models.Model):
    _inherit = "product.template"

    boteco_produzido_cozinha = fields.Boolean(
        "Produzido na cozinha central",
        help="Aparece no plano de produção e na tela de produção. Ganha lote e etiqueta ao ser produzido.",
    )
    boteco_conservacao = fields.Selection(CONSERVACOES, string="Conservação", default="congelado")
    boteco_validade_resfriado_dias = fields.Integer(
        "Validade resfriado (dias)", help="Se o produto for mantido resfriado em vez de congelado.")
    boteco_dias_cobertura = fields.Integer(
        "Dias de estoque a manter", default=2, help="O plano de produção sugere o suficiente para estes dias.")

    @api.onchange("boteco_produzido_cozinha")
    def _onchange_boteco_produzido_cozinha(self):
        if self.boteco_produzido_cozinha:
            self.tracking = "lot"
            self.is_storable = True
            self.use_expiration_date = True
            if not self.expiration_time:
                self.expiration_time = 90

    def boteco_texto_conservacao(self):
        self.ensure_one()
        return TEXTO_CONSERVACAO.get(self.boteco_conservacao or "congelado")

    def _boteco_configurar_lote(self):
        """Produto da cozinha central: estoque controlado, por lote e com validade."""
        for tmpl in self.filtered("boteco_produzido_cozinha"):
            vals = {}
            if not tmpl.is_storable:
                vals["is_storable"] = True
            if tmpl.tracking != "lot":
                vals["tracking"] = "lot"
            if not tmpl.use_expiration_date:
                vals["use_expiration_date"] = True
            if not tmpl.expiration_time:
                vals["expiration_time"] = 90
            if vals:
                super(ProductTemplate, tmpl).write(vals)
                # As variantes leem estes campos do modelo: descarta o que estava em cache
                tmpl.product_variant_ids.invalidate_recordset(list(vals))

    @api.model_create_multi
    def create(self, vals_list):
        templates = super().create(vals_list)
        templates._boteco_configurar_lote()
        return templates

    def write(self, vals):
        res = super().write(vals)
        if "boteco_produzido_cozinha" in vals:
            self._boteco_configurar_lote()
        return res


class ProductProduct(models.Model):
    _inherit = "product.product"

    @api.model_create_multi
    def create(self, vals_list):
        produtos = super().create(vals_list)
        # Criando direto a variante, o cache dela guarda os valores padrão (sem lote): reconfigura e limpa
        produtos.product_tmpl_id._boteco_configurar_lote()
        produtos.invalidate_recordset(["tracking", "is_storable", "use_expiration_date", "expiration_time"])
        return produtos
