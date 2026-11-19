from odoo import _, fields, models
from odoo.exceptions import UserError
from odoo.tools import float_compare


class StockPicking(models.Model):
    _inherit = "stock.picking"

    boteco_separado = fields.Boolean("Separado (lido pelo QR)", copy=False, readonly=True)
    boteco_separado_por_id = fields.Many2one("res.users", string="Separado por", copy=False, readonly=True)

    def boteco_dados_separacao(self):
        self.ensure_one()
        itens = []
        for move in self.move_ids.filtered(lambda m: m.state not in ("done", "cancel")):
            itens.append({
                "produto": move.product_id.display_name,
                "pedido": move.product_uom_qty,
                "separado": sum(move.move_line_ids.filtered(lambda ml: ml.lot_id and ml.picked).mapped("quantity")),
                "unidade": move.product_uom.name,
                "lotes": [{"lote": ml.lot_id.name, "quantidade": ml.quantity,
                           "validade": ml.lot_id.expiration_date.strftime("%d/%m/%Y") if ml.lot_id.expiration_date else ""}
                          for ml in move.move_line_ids.filtered(lambda ml: ml.lot_id and ml.picked)],
            })
        return {"id": self.id, "nome": self.name, "destino": self.partner_id.display_name or self.location_dest_id.display_name,
                "tipo": self.picking_type_code, "estado": self.state, "separado": self.boteco_separado, "itens": itens}

    def boteco_ler_lote(self, codigo):
        """QR da etiqueta lido: coloca o lote no item certo (respeita validade e quantidade pedida)."""
        self.ensure_one()
        if self.state in ("done", "cancel"):
            raise UserError(_("Esta transferência já foi concluída."))
        codigo = (codigo or "").strip()
        lote = self.env["stock.lot"].search([("name", "=", codigo), ("product_id", "in", self.move_ids.product_id.ids)], limit=1)
        if not lote:
            raise UserError(_("O lote %s não é de nenhum produto desta lista.", codigo))
        if lote.boteco_vencido():
            raise UserError(_("Lote %s VENCIDO: não pode sair. Separe outro e registre a perda deste.", lote.name))
        move = self.move_ids.filtered(lambda m: m.product_id == lote.product_id and m.state not in ("done", "cancel"))[:1]
        if move:
            # Leitor que dispara duas vezes (ou dois aparelhos): a 2a leitura espera a 1a terminar e vê o lote já lido
            self.env.cr.execute("SELECT id FROM stock_move WHERE id = %s FOR UPDATE", [move.id])
            move.invalidate_recordset(["move_line_ids"])
            move.move_line_ids.invalidate_recordset()
        ja_lido = move.move_line_ids.filtered(lambda ml: ml.lot_id == lote and ml.picked)
        if ja_lido:
            raise UserError(_("O lote %s já foi lido.", lote.name))
        separado = sum(move.move_line_ids.filtered(lambda ml: ml.lot_id and ml.picked).mapped("quantity"))
        falta = move.product_uom_qty - separado
        if float_compare(falta, 0, precision_rounding=move.product_uom.rounding) <= 0:
            raise UserError(_("%s já está completo.", move.product_id.display_name))
        # Reservas automáticas (não lidas) deste item dão lugar às linhas lidas pelo QR. Antes de olhar o saldo:
        # senão a reserva do próprio item era descontada (lote de 9,6 kg com 5 kg pedidos separava só 4,6 kg).
        move.move_line_ids.filtered(lambda ml: not ml.picked).unlink()
        quant = self.env["stock.quant"].search([
            ("lot_id", "=", lote.id), ("location_id", "child_of", self.location_id.id), ("quantity", ">", 0)], limit=1)
        if not quant:
            raise UserError(_("Não há saldo do lote %s no estoque de origem.", lote.name))
        quantidade = min(falta, quant.quantity - quant.reserved_quantity) or min(falta, quant.quantity)
        self.env["stock.move.line"].create({
            "move_id": move.id, "picking_id": self.id, "product_id": move.product_id.id, "lot_id": lote.id,
            "quantity": quantidade, "product_uom_id": move.product_uom.id, "picked": True,
            "location_id": quant.location_id.id, "location_dest_id": move.location_dest_id.id,
        })
        move.picked = True
        return _("%(qtd)s %(un)s de %(prod)s (lote %(lote)s)", qtd=quantidade, un=move.product_uom.name,
                 prod=move.product_id.display_name, lote=lote.name)

    def boteco_concluir_separacao(self):
        """Saída para cliente: conclui a entrega. Transferência para o bar: fica esperando o bar confirmar."""
        self.ensure_one()
        faltando = self.move_ids.filtered(
            lambda m: m.product_id.tracking != "none" and not m.move_line_ids.filtered(lambda ml: ml.lot_id and ml.picked))
        if faltando:
            raise UserError(_("Leia o QR das etiquetas de: %s", ", ".join(faltando.product_id.mapped("display_name"))))
        self.write({"boteco_separado": True, "boteco_separado_por_id": self.env.user.id})
        if self.picking_type_code == "outgoing":
            self.with_context(skip_backorder=True, picking_ids_not_to_backorder=self.ids).button_validate()
        return True

    def action_boteco_confirmar_recebimento(self):
        """No bar: confere e confirma que chegou (conclui a transferência da cozinha central)."""
        for picking in self:
            if not picking.boteco_separado:
                raise UserError(_("A cozinha ainda não separou %s.", picking.name))
            picking.with_context(skip_backorder=True, picking_ids_not_to_backorder=picking.ids).button_validate()
        return True

    def action_boteco_abrir_separacao(self):
        self.ensure_one()
        return {"type": "ir.actions.act_url", "url": "/boteco/separacao/%s" % self.id, "target": "self"}
