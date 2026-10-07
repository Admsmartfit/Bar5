from odoo import models


class PosOrderLine(models.Model):
    _inherit = "pos.order.line"

    def _boteco_bom_kit(self):
        self.ensure_one()
        return self.env["mrp.bom"]._bom_find(self.product_id, company_id=self.company_id.id, bom_type="phantom").get(
            self.product_id)

    def _compute_total_cost(self, stock_moves):
        """Produto com ficha técnica do tipo kit: custo = soma dos insumos (custo médio de cada um).

        O Odoo usaria o custo cadastrado no próprio kit (normalmente zero), o que deixaria o CMV errado.
        """
        kits = self.env["pos.order.line"]
        for linha in self.filtered(lambda l: not l.is_total_cost_computed):
            bom = linha._boteco_bom_kit()
            if not bom:
                continue
            _boms, componentes = bom.explode(linha.product_id, linha.qty / (bom.product_qty or 1.0))
            custo = 0.0
            for bom_line, dados in componentes:
                produto = bom_line.product_id
                qtd = bom_line.product_uom_id._compute_quantity(dados["qty"], produto.uom_id)
                custo += qtd * produto.standard_price
            linha.total_cost = custo
            linha.is_total_cost_computed = True
            kits |= linha
        return super(PosOrderLine, self - kits)._compute_total_cost(stock_moves)
