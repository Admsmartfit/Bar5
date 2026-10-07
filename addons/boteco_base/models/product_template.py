from odoo import _, models

# Preço de venda é auditado no modelo (product.template); o custo é por variante
# (product.product.standard_price), pois o custo do modelo apenas repassa às variantes.
# Assim cada alteração gera uma única linha de auditoria.
CAMPOS_PRECO_AUDITADOS = {
    "list_price": "Preço de venda",
}


class ProductTemplate(models.Model):
    _inherit = "product.template"

    def _boteco_campos_preco_auditados(self):
        """Campos de preço que entram na auditoria. Outros módulos acrescentam (ex.: happy hour)."""
        return dict(CAMPOS_PRECO_AUDITADOS)

    def write(self, vals):
        campos = {k: v for k, v in self._boteco_campos_preco_auditados().items() if k in vals}
        antes = {p.id: {c: p[c] for c in campos} for p in self} if campos else {}
        res = super().write(vals)
        if campos:
            Auditoria = self.env["boteco.auditoria"]
            for produto in self:
                for campo, rotulo in campos.items():
                    velho, novo = antes[produto.id][campo], produto[campo]
                    if (velho or 0.0) != (novo or 0.0):
                        Auditoria.registrar(
                            "alteracao_preco",
                            registro=produto,
                            descricao=_("%(rotulo)s: %(produto)s", rotulo=rotulo, produto=produto.display_name),
                            valor_antigo="%.2f" % (velho or 0.0),
                            valor_novo="%.2f" % (novo or 0.0),
                            valor=(novo or 0.0) - (velho or 0.0),
                        )
        return res


class ProductProduct(models.Model):
    _inherit = "product.product"

    def write(self, vals):
        # disable_auto_svl = custo médio recalculado pelo estoque (entrada de compra): não é
        # alteração manual de preço e geraria uma linha de auditoria por recebimento.
        if "standard_price" not in vals or self.env.context.get("disable_auto_svl"):
            return super().write(vals)
        antes = {p.id: p.standard_price for p in self}
        res = super().write(vals)
        Auditoria = self.env["boteco.auditoria"]
        for produto in self:
            if antes[produto.id] != produto.standard_price:
                Auditoria.registrar(
                    "alteracao_preco",
                    registro=produto,
                    descricao=_("Custo: %s", produto.display_name),
                    valor_antigo="%.2f" % antes[produto.id],
                    valor_novo="%.2f" % produto.standard_price,
                    valor=produto.standard_price - antes[produto.id],
                )
        return res
