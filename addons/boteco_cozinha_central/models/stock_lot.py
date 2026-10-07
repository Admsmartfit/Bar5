from datetime import timedelta

from odoo import _, api, fields, models

DIAS_ALERTA = 3


class StockLot(models.Model):
    _inherit = "stock.lot"

    boteco_fabricacao = fields.Date("Fabricação")
    boteco_peso = fields.Float("Peso produzido (kg)", digits="Product Unit of Measure")
    boteco_producao_id = fields.Many2one("mrp.production", string="Produção", readonly=True)
    boteco_situacao = fields.Selection(
        [("ok", "Dentro da validade"), ("vencendo", "Vence em até 3 dias"), ("vencido", "Vencido")],
        string="Situação", compute="_compute_boteco_situacao", search="_search_boteco_situacao",
    )

    @api.depends("expiration_date")
    def _compute_boteco_situacao(self):
        agora = fields.Datetime.now()
        for lote in self:
            if not lote.expiration_date:
                lote.boteco_situacao = "ok"
            elif lote.expiration_date <= agora:
                lote.boteco_situacao = "vencido"
            elif lote.expiration_date <= agora + timedelta(days=DIAS_ALERTA):
                lote.boteco_situacao = "vencendo"
            else:
                lote.boteco_situacao = "ok"

    def _search_boteco_situacao(self, operator, value):
        agora = fields.Datetime.now()
        limite = agora + timedelta(days=DIAS_ALERTA)
        dominios = {
            "vencido": [("expiration_date", "<=", agora)],
            "vencendo": [("expiration_date", ">", agora), ("expiration_date", "<=", limite)],
            "ok": ["|", ("expiration_date", "=", False), ("expiration_date", ">", limite)],
        }
        if operator == "=" and value in dominios:
            return dominios[value]
        if operator == "in":
            dominio = []
            for v in value:
                dominio = ["|"] + dominio + dominios[v] if dominio else dominios[v]
            return dominio
        return []

    def boteco_vencido(self):
        self.ensure_one()
        return bool(self.expiration_date and self.expiration_date <= fields.Datetime.now())

    # ------------------------------------------------------------------ rastreio
    def boteco_rastreio(self):
        """De onde veio (insumos e lotes consumidos) e para onde foi (bar, clientes)."""
        self.ensure_one()
        MoveLine = self.env["stock.move.line"].sudo()
        insumos = []
        producao = self.boteco_producao_id or self.env["mrp.production"].sudo().search(
            [("lot_producing_id", "=", self.id), ("state", "=", "done")], limit=1)
        if producao:
            for ml in producao.move_raw_ids.move_line_ids:
                insumos.append({
                    "produto": ml.product_id.display_name,
                    "lote": ml.lot_id.name or "",
                    "quantidade": ml.quantity,
                    "unidade": ml.product_uom_id.name,
                })
        destinos = []
        saidas = MoveLine.search([("lot_id", "=", self.id), ("state", "=", "done")], order="date asc")
        armazens = self.env["stock.warehouse"].sudo().search([])
        for ml in saidas:
            destino = ml.location_dest_id
            if destino.usage == "customer":
                quem = ml.picking_id.partner_id.commercial_partner_id
                destinos.append({"tipo": "cliente", "destino": quem.display_name or destino.display_name,
                                 "partner_id": quem.id, "data": fields.Datetime.to_string(ml.date),
                                 "quantidade": ml.quantity, "documento": ml.picking_id.name or ml.reference})
            elif destino.usage == "internal" and ml.location_id.usage == "internal":
                armazem = armazens.filtered(lambda w, d=destino: d.parent_path.startswith(w.view_location_id.parent_path))[:1]
                origem = armazens.filtered(lambda w, o=ml.location_id: o.parent_path.startswith(w.view_location_id.parent_path))[:1]
                if armazem and armazem != origem:
                    destinos.append({"tipo": "unidade", "destino": armazem.name, "partner_id": False,
                                     "data": fields.Datetime.to_string(ml.date), "quantidade": ml.quantity,
                                     "documento": ml.picking_id.name or ml.reference})
        return {
            "lote": self.name,
            "produto": self.product_id.display_name,
            "fabricacao": fields.Date.to_string(self.boteco_fabricacao) if self.boteco_fabricacao else "",
            "validade": fields.Datetime.to_string(self.expiration_date) if self.expiration_date else "",
            "insumos": insumos,
            "destinos": destinos,
            "clientes": sorted({d["destino"] for d in destinos if d["tipo"] == "cliente"}),
        }

    @api.model
    def boteco_buscar_rastreio(self, codigo):
        lote = self.sudo().search([("name", "=", (codigo or "").strip())], limit=1)
        return lote.boteco_rastreio() if lote else {"erro": _("Lote %s não encontrado.", codigo)}

    def action_boteco_etiqueta(self):
        """Reimprime a etiqueta do lote."""
        for lote in self:
            producao = lote.boteco_producao_id
            if producao:
                producao._boteco_imprimir_etiqueta()
        return True
