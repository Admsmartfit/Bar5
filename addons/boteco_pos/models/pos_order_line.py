from odoo import _, api, fields, models
from odoo.exceptions import UserError
from odoo.tools import float_compare, float_is_zero


class PosOrderLine(models.Model):
    _inherit = "pos.order.line"

    boteco_qtd_enviada = fields.Float("Qtd. já enviada à produção", copy=False, readonly=True)
    boteco_cortesia = fields.Boolean("Cortesia", copy=False)
    boteco_motivo = fields.Char("Motivo (desconto/cortesia)", copy=False)
    boteco_autorizacao_ref = fields.Integer("Autorização", copy=False)
    boteco_autorizado_por_id = fields.Many2one("res.users", string="Autorizado por", copy=False, readonly=True)

    @api.model
    def _load_pos_data_fields(self, config_id):
        campos = super()._load_pos_data_fields(config_id)
        return campos + ["boteco_qtd_enviada", "boteco_cortesia", "boteco_motivo", "boteco_autorizacao_ref"]

    # ------------------------------------------------------------------
    # Desconto e cortesia: só com permissão ou PIN do gerente
    # ------------------------------------------------------------------
    def _boteco_conferir_desconto(self, antes=None):
        antes = antes or {}
        digitos = self.env["decimal.precision"].precision_get("Discount")
        for linha in self:
            pedido = linha.order_id
            if pedido.boteco_tipo_conta == "funcionario" or linha.qty <= 0:
                continue
            desconto_antes = antes.get(linha.id, 0.0)
            if float_compare(linha.discount or 0.0, desconto_antes, precision_digits=digitos) <= 0:
                continue  # só controla aumento de desconto
            permissao = "pode_dar_cortesia" if linha.boteco_cortesia else "pode_dar_desconto"
            autorizado_por = pedido.session_id._boteco_exigir(
                permissao, linha.boteco_autorizacao_ref or None, referencia=None
            )
            super(PosOrderLine, linha).write({"boteco_autorizado_por_id": autorizado_por.id})
            valor = linha.price_unit * linha.qty * (linha.discount - desconto_antes) / 100.0
            self.env["boteco.auditoria"].registrar(
                "cortesia" if linha.boteco_cortesia else "desconto",
                registro=pedido,
                descricao=_("%(tipo)s: %(qtd)s x %(item)s (%(pct)s%%)", tipo=_("Cortesia") if linha.boteco_cortesia else _("Desconto"),
                            qtd=linha.qty, item=linha.full_product_name or linha.product_id.display_name, pct=linha.discount),
                valor=valor, motivo=linha.boteco_motivo, autorizado_por=autorizado_por, referencia=linha.uuid,
            )

    # ------------------------------------------------------------------
    # Cancelamento de item já enviado: só com PIN do gerente e motivo
    # ------------------------------------------------------------------
    def _boteco_conferir_cancelamento(self, qtd_nova):
        """qtd_nova: {line_id: nova quantidade} (0 = linha apagada)."""
        if self.env.context.get("boteco_sistema"):
            return
        for linha in self:
            enviada = linha.boteco_qtd_enviada or 0.0
            nova = qtd_nova.get(linha.id, linha.qty)
            if float_is_zero(enviada, precision_digits=3) or float_compare(nova, enviada, precision_digits=3) >= 0:
                continue
            if linha.order_id.state != "draft":
                continue
            pedido = linha.order_id
            Autorizacao = self.env["boteco.autorizacao"]
            autorizacao = Autorizacao.consumir("pode_cancelar_item", referencia=linha.uuid)
            if not autorizacao:
                # Autorização para a conta inteira (cancelar pedido): vale para todas as linhas
                # dentro da mesma transação.
                cache = self.env.cr.cache.setdefault("boteco_autorizacao_pedido", {})
                if pedido.uuid in cache:
                    autorizacao = Autorizacao.browse(cache[pedido.uuid])
                else:
                    autorizacao = Autorizacao.consumir("pode_cancelar_item", referencia=pedido.uuid)
                    if autorizacao:
                        cache[pedido.uuid] = autorizacao.id
            autorizado_por = autorizacao.autorizado_por_id if autorizacao else None
            if not autorizacao and not self.env.user.boteco_pode("pode_cancelar_item"):
                raise UserError(_(
                    "%(item)s já foi para a produção. Cancelar só com o PIN do gerente e o motivo.",
                    item=linha.full_product_name or linha.product_id.display_name,
                ))
            cancelada = enviada - nova
            self.env["boteco.auditoria"].registrar(
                "cancelar_item",
                registro=pedido,
                descricao=_("Cancelado: %(qtd)s x %(item)s%(mesa)s", qtd=cancelada,
                            item=linha.full_product_name or linha.product_id.display_name,
                            mesa=_(" – mesa %s", pedido.table_id.table_number) if pedido.table_id else ""),
                valor=cancelada * linha.price_unit * (1 - (linha.discount or 0.0) / 100.0),
                motivo=autorizacao.motivo if autorizacao else _("Cancelado por quem tem permissão"),
                autorizado_por=autorizado_por or self.env.user,
                referencia=linha.uuid,
            )

    @api.model_create_multi
    def create(self, vals_list):
        linhas = super().create(vals_list)
        linhas.filtered(lambda l: l.discount)._boteco_conferir_desconto()
        return linhas

    def write(self, vals):
        if self.env.context.get("boteco_sistema"):
            return super().write(vals)
        if "qty" in vals:
            self._boteco_conferir_cancelamento({linha.id: vals["qty"] for linha in self})
        desconto_antes = {l.id: l.discount for l in self} if "discount" in vals else None
        res = super().write(vals)
        if desconto_antes is not None:
            self._boteco_conferir_desconto(desconto_antes)
        return res

    def unlink(self):
        if not self.env.context.get("boteco_sistema"):
            self._boteco_conferir_cancelamento({linha.id: 0.0 for linha in self})
        return super().unlink()
