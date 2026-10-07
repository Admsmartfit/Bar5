"""Lista de compras sugerida: tudo abaixo do mínimo, por fornecedor, com link de WhatsApp."""

import re
from urllib.parse import quote

from odoo import _, fields, models


class BotecoListaCompras(models.TransientModel):
    _name = "boteco.lista.compras"
    _description = "Lista de compras sugerida"

    linha_ids = fields.One2many("boteco.lista.compras.linha", "lista_id", string="Fornecedores")

    def action_gerar(self):
        self.ensure_one()
        regras = self.env["stock.warehouse.orderpoint"].search([("company_id", "=", self.env.company.id)])
        por_fornecedor = {}
        for regra in regras:
            produto = regra.product_id
            disponivel = produto.with_context(location=regra.location_id.id).qty_available
            if disponivel >= regra.product_min_qty:
                continue
            comprar = max(regra.product_max_qty, regra.product_min_qty) - disponivel
            vendedor = produto.seller_ids[:1]
            fornecedor = vendedor.partner_id
            por_fornecedor.setdefault(fornecedor.id or 0, []).append(
                (produto, comprar, disponivel, regra.product_min_qty, vendedor.product_code))
        linhas = [fields.Command.clear()]
        empresa = self.env.company.name
        for fornecedor_id, itens in por_fornecedor.items():
            fornecedor = self.env["res.partner"].browse(fornecedor_id)
            texto_itens = "\n".join(
                "• %s: %s %s%s" % (p.name, ("%g" % qtd), p.uom_po_id.name or p.uom_id.name, " (cód. %s)" % cod if cod else "")
                for p, qtd, _disp, _min, cod in itens
            )
            mensagem = _("Olá! Pedido do %(empresa)s:\n%(itens)s\nObrigado!", empresa=empresa, itens=texto_itens)
            telefone = re.sub(r"\D", "", fornecedor.mobile or fornecedor.phone or "")
            if telefone and not telefone.startswith("55"):
                telefone = "55" + telefone
            linhas.append(fields.Command.create({
                "partner_id": fornecedor.id or False,
                "itens": texto_itens,
                "mensagem": mensagem,
                "link_whatsapp": "https://wa.me/%s?text=%s" % (telefone, quote(mensagem)) if telefone
                else "https://wa.me/?text=%s" % quote(mensagem),
                "quantidade_itens": len(itens),
            }))
        self.linha_ids = linhas
        return {"type": "ir.actions.act_window", "res_model": self._name, "res_id": self.id, "view_mode": "form",
                "target": "new"}


class BotecoListaComprasLinha(models.TransientModel):
    _name = "boteco.lista.compras.linha"
    _description = "Lista de compras por fornecedor"

    lista_id = fields.Many2one("boteco.lista.compras", required=True, ondelete="cascade")
    partner_id = fields.Many2one("res.partner", string="Fornecedor")
    quantidade_itens = fields.Integer("Itens")
    itens = fields.Text("O que comprar")
    mensagem = fields.Text("Mensagem")
    link_whatsapp = fields.Char("WhatsApp")

    def action_abrir_whatsapp(self):
        self.ensure_one()
        return {"type": "ir.actions.act_url", "url": self.link_whatsapp, "target": "new"}
