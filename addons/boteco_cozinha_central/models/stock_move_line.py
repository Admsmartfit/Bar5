from odoo import _, models
from odoo.exceptions import UserError


class StockMoveLine(models.Model):
    _inherit = "stock.move.line"

    def _action_done(self):
        """Lote vencido não sai do lugar (transferência, venda, consumo). Só descarte (perda)."""
        for ml in self:
            lote = ml.lot_id
            if not lote or not lote.expiration_date or ml.move_id.scrapped:
                continue
            if ml.location_dest_id.usage in ("inventory",) or ml.location_id.usage != "internal":
                continue
            if lote.boteco_vencido():
                raise UserError(_(
                    "O lote %(lote)s de %(produto)s venceu em %(data)s e está bloqueado. "
                    "Registre a perda em vez de transferir ou vender.",
                    lote=lote.name, produto=ml.product_id.display_name,
                    data=lote.expiration_date.strftime("%d/%m/%Y"),
                ))
        return super()._action_done()
