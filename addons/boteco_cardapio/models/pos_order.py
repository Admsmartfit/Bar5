from odoo import api, fields, models
from odoo.tools import float_compare


class PosOrderLine(models.Model):
    _inherit = "pos.order.line"

    boteco_oferta_id = fields.Many2one("boteco.oferta.relampago", string="Oferta relâmpago", index="btree_not_null",
                                       readonly=True)
    boteco_preco_origem = fields.Selection(
        [("normal", "Normal"), ("happy", "Happy hour"), ("oferta", "Oferta relâmpago")],
        string="Preço aplicado", default="normal", readonly=True,
    )
    boteco_preco_fixado = fields.Float(
        "Preço fixado", digits="Product Price", readonly=True, copy=False,
        help="Preço no momento do pedido. O autoatendimento recalcula os preços a cada envio; "
        "com isso, um chope pedido às 20h59 continua no preço de happy hour depois das 21h.",
    )

    @api.model
    def _load_pos_data_fields(self, config_id):
        campos = super()._load_pos_data_fields(config_id)
        return campos + ["boteco_preco_origem"] if campos else campos

    @api.model_create_multi
    def create(self, vals_list):
        linhas = super().create(vals_list)
        linhas._boteco_vincular_promocao()
        return linhas

    def write(self, vals):
        res = super().write(vals)
        if "qty" in vals:
            self.boteco_oferta_id._atualizar_estado()
        return res

    def _boteco_vincular_promocao(self):
        """Identifica o preço promocional de cada linha nova e baixa o saldo da oferta."""
        ofertas = self.env["boteco.oferta.relampago"]
        digitos = self.env["decimal.precision"].precision_get("Product Price")
        for linha in self:
            if linha.qty <= 0 or linha.boteco_oferta_id:
                continue
            promo = linha.product_id._boteco_preco_promocional(qtd=linha.qty)
            if not promo:
                continue
            preco, origem, oferta = promo
            preco_linha = linha.price_unit - (linha.price_extra or 0.0)
            if float_compare(preco_linha, preco, precision_digits=digitos) != 0:
                continue  # caixa digitou outro preço: não é promoção
            vals = {"boteco_preco_origem": origem}
            if oferta:
                vals["boteco_oferta_id"] = oferta.id
                ofertas |= oferta
            linha.write(vals)
        ofertas._atualizar_estado()


class PosOrder(models.Model):
    _inherit = "pos.order"

    def _compute_line_price(self, line):
        """Autoatendimento (tablet/QR): o servidor recalcula o preço de cada linha a cada envio.

        * Linha já gravada mantém o preço do momento em que foi pedida (boteco_preco_fixado).
        * Linha nova recebe o preço promocional vigente (oferta relâmpago ou happy hour).
        """
        super()._compute_line_price(line)
        extra = sum(line.attribute_value_ids.mapped("price_extra"))
        if line.boteco_preco_fixado:
            preco = line.boteco_preco_fixado
        elif line.boteco_oferta_id:
            # Já vinculada na criação da linha (o saldo da oferta já conta com ela)
            preco = line.boteco_oferta_id.preco + extra
            line.boteco_preco_fixado = preco
        else:
            promo = line.product_id._boteco_preco_promocional(qtd=line.qty)
            if promo:
                preco_base, origem, oferta = promo
                preco = preco_base + extra
                line.boteco_preco_origem = origem
                if oferta:
                    line.boteco_oferta_id = oferta
            else:
                preco = line.price_unit
            line.boteco_preco_fixado = preco
        if preco != line.price_unit:
            line.price_unit = preco
            taxes = self.fiscal_position_id.map_tax(line.tax_ids)
            res = taxes.compute_all(preco, self.currency_id, line.qty, product=line.product_id, partner=self.partner_id)
            line.price_subtotal = res["total_excluded"]
            line.price_subtotal_incl = res["total_included"]
        line.boteco_oferta_id._atualizar_estado()
