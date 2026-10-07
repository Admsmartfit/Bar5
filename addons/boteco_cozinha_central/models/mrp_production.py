import logging

from odoo import _, api, fields, models
from odoo.exceptions import UserError

from ..tools import etiqueta

_logger = logging.getLogger(__name__)


class MrpProduction(models.Model):
    _inherit = "mrp.production"

    boteco_iniciado_em = fields.Datetime("Começou em", readonly=True, copy=False)
    boteco_peso_real = fields.Float("Peso real", digits="Product Unit of Measure", readonly=True, copy=False)
    boteco_rendimento_pct = fields.Float("Rendimento real (%)", readonly=True, copy=False,
                                         help="Peso real dividido pelo previsto na receita.")
    boteco_rendimento_esperado_pct = fields.Float(
        "Rendimento esperado (%)", compute="_compute_boteco_rendimento_esperado")

    @api.depends("bom_id.boteco_perda_esperada")
    def _compute_boteco_rendimento_esperado(self):
        for producao in self:
            producao.boteco_rendimento_esperado_pct = 100.0 - (producao.bom_id.boteco_perda_esperada or 0.0)

    # ------------------------------------------------------------------ lote
    def _prepare_stock_lot_values(self):
        vals = super()._prepare_stock_lot_values()
        if self.product_id.boteco_produzido_cozinha:
            vals["name"] = self.env["ir.sequence"].next_by_code("boteco.lote.cozinha") or vals.get("name")
            vals["boteco_fabricacao"] = fields.Date.context_today(self)
            vals["boteco_producao_id"] = self.id
        return vals

    # ------------------------------------------------------------------ tela de produção
    @api.model
    def boteco_dados_tela(self):
        """Produções do dia para a tela do tablet (sem teclado, exceto o peso)."""
        producoes = self.search([
            ("company_id", "in", self.env.companies.ids),
            ("state", "in", ("confirmed", "progress", "to_close")),
        ], order="date_start asc, id asc", limit=50)
        return [producao._boteco_dados() for producao in producoes]

    def _boteco_dados(self):
        self.ensure_one()
        return {
            "id": self.id,
            "nome": self.name,
            "produto": self.product_id.display_name,
            "imagem": "/web/image/product.product/%s/image_256" % self.product_id.id,
            "quantidade": self.product_qty,
            "unidade": self.product_uom_id.name,
            "estado": "fazendo" if self.boteco_iniciado_em else "fila",
            "iniciado_em": fields.Datetime.to_string(self.boteco_iniciado_em) if self.boteco_iniciado_em else False,
            "conservacao": self.product_id.product_tmpl_id.boteco_texto_conservacao(),
            "modo_preparo": self.bom_id.boteco_modo_preparo or "",
            "insumos": [
                {"nome": m.product_id.display_name, "quantidade": m.product_uom_qty, "unidade": m.product_uom.name}
                for m in self.move_raw_ids
            ],
        }

    def boteco_iniciar(self):
        for producao in self:
            if producao.state == "draft":
                producao.action_confirm()
            producao.boteco_iniciado_em = producao.boteco_iniciado_em or fields.Datetime.now()
        return [p._boteco_dados() for p in self]

    def boteco_finalizar(self, peso):
        """Fecha a produção com o peso real: lote, validade, baixa dos insumos, etiqueta."""
        self.ensure_one()
        try:
            peso = float(peso)
        except (TypeError, ValueError):
            raise UserError(_("Digite o peso que saiu na balança.")) from None
        if peso <= 0:
            raise UserError(_("Digite o peso que saiu na balança."))
        if self.state == "draft":
            self.action_confirm()
        if not self.boteco_iniciado_em:
            self.boteco_iniciado_em = fields.Datetime.now()
        if self.product_id.tracking != "none" and not self.lot_producing_id:
            self._set_lot_producing()
        self.qty_producing = peso
        self._set_qty_producing(False)
        # Os insumos são os da receita inteira, não proporcionais ao peso (o que sobrou de peso é perda)
        for move in self.move_raw_ids.filtered(lambda m: m.state not in ("done", "cancel")):
            move.quantity = move.product_uom_qty
            move.picked = True
        lote = self.lot_producing_id  # guardado antes: o fechamento pode limpar o campo
        resultado = self.with_context(skip_backorder=True, mo_ids_to_backorder=[], skip_consumption=True,
                                      skip_redirection=True).button_mark_done()
        if self.state != "done":
            _logger.warning("Produção %s não fechou: %s (estado %s)", self.name, resultado, self.state)
            raise UserError(_("Não deu para fechar a produção %s. Chame o gerente.", self.name))
        self.write({
            "boteco_peso_real": peso,
            "boteco_rendimento_pct": round(peso * 100.0 / self.product_qty, 1) if self.product_qty else 0.0,
        })
        if lote:
            if not self.lot_producing_id:
                self.lot_producing_id = lote
            lote.write({"boteco_peso": peso, "boteco_producao_id": self.id,
                        "boteco_fabricacao": lote.boteco_fabricacao or fields.Date.context_today(self)})
        impresso = self._boteco_imprimir_etiqueta()
        return {
            "lote": lote.name or "",
            "validade": lote.expiration_date.strftime("%d/%m/%Y") if lote and lote.expiration_date else "",
            "rendimento": self.boteco_rendimento_pct,
            "etiqueta": impresso,
        }

    # ------------------------------------------------------------------ etiqueta
    def _boteco_dados_etiqueta(self):
        self.ensure_one()
        lote = self.lot_producing_id
        empresa = self.company_id
        unidade = self.product_uom_id.name
        peso = self.boteco_peso_real or self.qty_producing or self.product_qty
        return {
            "produto": self.product_id.name,
            "fabricacao": (lote.boteco_fabricacao or fields.Date.context_today(self)).strftime("%d/%m/%Y"),
            "validade": lote.expiration_date.strftime("%d/%m/%Y") if lote.expiration_date else "-",
            "lote": lote.name or "-",
            "peso": ("%.3f %s" % (peso, unidade)).replace(".", ","),
            "conservacao": self.product_id.product_tmpl_id.boteco_texto_conservacao(),
            "empresa": empresa.name,
            "cnpj": empresa.vat or "-",
            "registro": empresa.boteco_registro_sanitario or "",
            "qr": lote.name or self.name,
        }

    def _boteco_impressora_etiqueta(self):
        self.ensure_one()
        armazem = self.picking_type_id.warehouse_id
        impressora = armazem.boteco_impressora_etiqueta_id
        if not impressora:
            impressora = self.env["boteco.impressora"].search(
                [("linguagem", "in", ("zpl", "tspl")), ("company_id", "in", (self.company_id.id, False))], limit=1)
        return impressora

    def _boteco_imprimir_etiqueta(self, copias=1):
        impresso = False
        for producao in self:
            impressora = producao._boteco_impressora_etiqueta()
            if not impressora:
                continue
            dados = producao._boteco_dados_etiqueta()
            dados["copias"] = copias
            conteudo = etiqueta.tspl(dados) if impressora.linguagem == "tspl" else etiqueta.zpl(dados)
            self.env["boteco.impressao.job"].enfileirar(impressora, _("Etiqueta %s", dados["lote"]), conteudo)
            impresso = True
        return impresso

    def action_boteco_reimprimir_etiqueta(self):
        if not self._boteco_imprimir_etiqueta():
            raise UserError(_("Cadastre a impressora de etiquetas no armazém da cozinha central."))
        return True
