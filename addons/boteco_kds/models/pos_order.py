from odoo import api, models


class PosOrder(models.Model):
    _inherit = "pos.order"

    def _boteco_ao_enviar(self, mudancas):
        """Cada envio ao bar/chapa vira ticket impresso e cartão na tela de produção."""
        res = super()._boteco_ao_enviar(mudancas)
        for pedido in self:
            self.env["boteco.kds.pedido"]._criar_dos_envios(pedido, mudancas)
        return res

    @api.model
    def boteco_status_itens(self, order_uuid):
        """Status de cada item (na fila, preparando, a caminho) – usado pela 'Minha conta' do tablet."""
        pedido = self.sudo().search([("uuid", "=", order_uuid)], limit=1)
        if not pedido:
            return {}
        itens = self.env["boteco.kds.item"].sudo().search([("pedido_id.order_id", "=", pedido.id),
                                                          ("pedido_id.tipo", "=", "novo")])
        status = {}
        for item in itens:
            status.setdefault(item.line_uuid, item.estado)
        return status

