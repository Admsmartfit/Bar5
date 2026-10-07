import logging

from odoo import models

_logger = logging.getLogger(__name__)


class StockPicking(models.Model):
    _inherit = "stock.picking"

    def _action_done(self):
        res = super()._action_done()
        self._boteco_faturar_entregas()
        return res

    def _boteco_faturar_entregas(self):
        """Entregou para o bar cliente: a conta a receber nasce na hora, com o prazo do cliente."""
        vendas = self.filtered(lambda p: p.picking_type_code == "outgoing" and p.state == "done").sale_id
        vendas = vendas.filtered(lambda v: v.partner_id.commercial_partner_id.boteco_cliente_b2b
                                 and v.invoice_status == "to invoice")
        for venda in vendas:
            faturas = venda.sudo()._create_invoices()
            faturas.action_post()
        return True
