from odoo import _, models
from odoo.exceptions import UserError


class StockScrap(models.Model):
    _inherit = "stock.scrap"

    def do_scrap(self):
        """Perda só com permissão (ou pelo gerente) e sempre com motivo; fica na auditoria."""
        user = self.env.user
        if not self.env.su and not user.boteco_pode("pode_ajustar_estoque"):
            raise UserError(_("Registrar perda precisa da permissão de ajustar estoque. Chame o gerente."))
        for scrap in self:
            if not scrap.scrap_reason_tag_ids:
                raise UserError(_("Escolha o motivo da perda (quebra, vencido, erro de preparo...)."))
        res = super().do_scrap()
        for scrap in self:
            self.env["boteco.auditoria"].registrar(
                "perda", registro=scrap,
                descricao=_("Perda: %(qtd)s %(un)s de %(prod)s", qtd=scrap.scrap_qty, un=scrap.product_uom_id.name,
                            prod=scrap.product_id.display_name),
                valor=scrap.scrap_qty * scrap.product_id.standard_price,
                motivo=", ".join(scrap.scrap_reason_tag_ids.mapped("name")),
            )
        return res
