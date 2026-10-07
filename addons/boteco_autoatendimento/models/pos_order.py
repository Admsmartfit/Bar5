from odoo import _, api, fields, models


class PosOrder(models.Model):
    _inherit = "pos.order"

    boteco_aguardando_garcom = fields.Boolean("Esperando o garçom (+18)", copy=False, index=True,
                                              help="Primeiro pedido com álcool da mesa: só vai para a produção depois que o "
                                              "garçom conferir a idade.")
    # Inteiro (não Many2one): o PDV carrega todos os campos do pedido e não conhece este modelo
    boteco_dispositivo_ref = fields.Integer("Aparelho (id)", copy=False, readonly=True)

    def _boteco_tem_alcool(self):
        self.ensure_one()
        return any(l.product_id.boteco_maior_18 and l.qty > 0 for l in self.lines)

    def _boteco_pos_autoatendimento(self, dispositivo):
        """Depois que o pedido do tablet/QR é gravado: origem, +18 e envio à produção."""
        for pedido in self.sudo():
            mesa = pedido.table_id
            vals = {"boteco_origem": "tablet" if dispositivo.tipo == "tablet" else "qr",
                    "boteco_dispositivo_ref": dispositivo.id}
            reter = bool(mesa) and pedido._boteco_tem_alcool() and not mesa.boteco_maior18_confirmado
            vals["boteco_aguardando_garcom"] = reter
            pedido.write(vals)
            if mesa:
                mesa._boteco_garantir_sessao()
            if reter:
                for config in mesa.floor_id.pos_config_ids:
                    if config.current_session_id:
                        config._notify("BOTECO_MAIOR18", {"mesa_id": mesa.id, "mesa": mesa.table_number, "pedido_id": pedido.id})
            else:
                pedido.boteco_marcar_enviado()
        return True

    def _boteco_resumo_mesa(self, mesa):
        """'Minha conta': todas as contas abertas da mesa, com status de cada item."""
        pedidos = self.sudo().search([("table_id", "=", mesa.id), ("state", "=", "draft")])
        status_por_linha = {}
        for pedido in pedidos:
            status_por_linha.update(self.boteco_status_itens(pedido.uuid))
        rotulo = {"aguardando": _("na fila"), "preparando": _("preparando"), "pronto": _("a caminho"),
                  "entregue": _("entregue")}
        config = pedidos[:1].config_id
        taxa_prod = config.boteco_produto_taxa_id
        couvert_prod = config.boteco_produto_couvert_id
        itens, consumo, couvert = [], 0.0, 0.0
        for linha in pedidos.lines.filtered(lambda l: l.qty > 0):
            if linha.product_id == taxa_prod:
                continue
            if linha.product_id == couvert_prod:
                couvert += linha.price_subtotal_incl
                continue
            consumo += linha.price_subtotal_incl
            estado = status_por_linha.get(linha.uuid)
            if linha.order_id.boteco_aguardando_garcom:
                estado_rotulo = _("esperando o garçom")
            elif estado:
                estado_rotulo = rotulo.get(estado, estado)
            elif linha.product_id.boteco_setor_id:
                estado_rotulo = _("enviado")
            else:
                estado_rotulo = ""
            itens.append({
                "nome": linha.full_product_name or linha.product_id.display_name,
                "quantidade": linha.qty,
                "total": linha.price_subtotal_incl,
                "status": estado_rotulo,
                "product_id": linha.product_id.id,
                "setor": linha.product_id.boteco_setor_id.codigo or "",
            })
        pct = config.boteco_taxa_servico_pct if config else 0.0
        taxa = round(consumo * pct / 100, 2) if pedidos and not all(pedidos.mapped("boteco_taxa_removida")) else 0.0
        if not couvert and config:
            agenda = self.env["boteco.agenda.musica"]._couvert_do_dia(config.company_id)
            pessoas = max(pedidos.mapped("customer_count") or [0]) or 1
            couvert = agenda.valor_couvert * pessoas if agenda else 0.0
        return {
            "itens": itens,
            "consumo": consumo,
            "taxa": taxa,
            "taxa_pct": pct,
            "couvert": couvert,
            "total": consumo + taxa + couvert,
        }

    @api.model
    def _boteco_bebidas_da_mesa(self, mesa):
        """'Pedir de novo': bebidas (setor bar) já pedidas na mesa, sem repetir."""
        pedidos = self.sudo().search([("table_id", "=", mesa.id), ("state", "=", "draft")])
        vistos, resultado = set(), []
        for linha in pedidos.lines.sorted("id", reverse=True):
            produto = linha.product_id
            if produto.id in vistos or produto.boteco_setor_id.codigo != "bar" or not produto.self_order_available:
                continue
            vistos.add(produto.id)
            resultado.append({"product_id": produto.id, "nome": produto.name})
        return resultado
