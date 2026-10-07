"""De onde nascem os registros fiscais: contas pagas do PDV, entregas B2B e perdas."""

from odoo import _, models

from .boteco_fiscal_registro import so_digitos


class PosOrder(models.Model):
    _inherit = "pos.order"

    def _boteco_registrar_fiscal(self):
        Registro = self.env["boteco.fiscal.registro"].sudo()
        existentes = set(Registro.search([("origem_model", "=", "pos.order"), ("origem_id", "in", self.ids)]).mapped("origem_id"))
        for pedido in self.filtered(lambda p: p.state in ("paid", "done", "invoiced") and p.id not in existentes):
            motivo = False
            if pedido.boteco_tipo_conta == "funcionario":
                motivo = _("Consumo de funcionário")
            elif pedido.amount_total <= 0:
                motivo = _("Cortesia total (sem valor)")
            Registro.create({
                "tipo": "nfce",
                "estado": "nao_emitir" if motivo else "pendente",
                "motivo_nao_emitir": motivo,
                "origem_model": "pos.order",
                "origem_id": pedido.id,
                "referencia": pedido.pos_reference or pedido.name,
                "data_venda": pedido.date_order,
                "dia": pedido.boteco_dia_operacao,
                "valor_total": pedido.amount_total,
                "taxa_servico": pedido.boteco_taxa_servico,
                "cliente_documento": so_digitos(pedido.boteco_cpf_nota) or so_digitos(pedido.partner_id.vat),
                "cliente_nome": pedido.partner_id.name or False,
                "company_id": pedido.company_id.id,
            })
        return True

    def _process_saved_order(self, draft):
        res = super()._process_saved_order(draft)
        self._boteco_registrar_fiscal()
        return res


class StockPicking(models.Model):
    _inherit = "stock.picking"

    def _action_done(self):
        res = super()._action_done()
        Registro = self.env["boteco.fiscal.registro"].sudo()
        for entrega in self.filtered(lambda p: p.picking_type_code == "outgoing" and p.state == "done" and p.sale_id):
            cliente = entrega.partner_id.commercial_partner_id
            if not cliente.boteco_cliente_b2b:
                continue
            if Registro.search_count([("origem_model", "=", "stock.picking"), ("origem_id", "=", entrega.id)]):
                continue
            valor = sum(m.sale_line_id.price_unit * m.quantity * (1 - (m.sale_line_id.discount or 0.0) / 100.0)
                        for m in entrega.move_ids if m.state == "done")
            Registro.create({
                "tipo": "nfe",
                "origem_model": "stock.picking",
                "origem_id": entrega.id,
                "referencia": "%s (%s)" % (entrega.name, entrega.sale_id.name),
                "data_venda": entrega.date_done,
                "dia": entrega.date_done.date(),
                "valor_total": valor,
                "cliente_documento": so_digitos(cliente.vat),
                "cliente_nome": cliente.name,
                "company_id": entrega.company_id.id,
            })
        return res


class StockScrap(models.Model):
    _inherit = "stock.scrap"

    def do_scrap(self):
        res = super().do_scrap()
        Registro = self.env["boteco.fiscal.registro"].sudo()
        for perda in self:
            Registro.create({
                "tipo": "nfce",
                "estado": "nao_emitir",
                "motivo_nao_emitir": _("Perda: %s", ", ".join(perda.scrap_reason_tag_ids.mapped("name")) or "-"),
                "origem_model": "stock.scrap",
                "origem_id": perda.id,
                "referencia": perda.name,
                "data_venda": perda.date_done,
                "dia": perda.date_done.date(),
                "valor_total": perda.scrap_qty * perda.product_id.standard_price,
                "company_id": perda.company_id.id,
            })
        return res
