/** @odoo-module */
// Numpad do pedido: diminuir/apagar item que já foi para a produção pede motivo e PIN do gerente.
import { patch } from "@web/core/utils/patch";
import { _t } from "@web/core/l10n/translation";
import { OrderSummary } from "@point_of_sale/app/screens/product_screen/order_summary/order_summary";
import { pedirAutorizacao } from "@boteco_pos/app/autorizacao_popup";
import { qtdEnviada } from "@boteco_pos/app/utils";

patch(OrderSummary.prototype, {
    _setValue(val) {
        const { numpadMode } = this.pos;
        let linha = this.currentOrder.get_selected_orderline();
        if (linha?.combo_parent_id) {
            linha = linha.combo_parent_id;
        }
        if (linha && numpadMode === "quantity" && !this._botecoLiberado) {
            const enviada = qtdEnviada(this.currentOrder, linha);
            const nova = val === "remove" ? 0 : parseFloat(val) || 0;
            if (enviada > 0 && nova < enviada) {
                this._botecoCancelar(linha, val, enviada - nova);
                return;
            }
        }
        return super._setValue(val);
    },

    async _botecoCancelar(linha, val, quantidade) {
        const aut = await pedirAutorizacao(this.pos, {
            permissao: "pode_cancelar_item",
            titulo: _t("Cancelar %s x %s", quantidade, linha.get_full_product_name()),
            subtitulo: _t("Este item já foi para a produção."),
            tipoMotivo: "cancelamento",
            referencia: linha.uuid,
            valor: quantidade * linha.get_unit_price(),
        });
        this.numberBuffer.reset();
        if (!aut) {
            return;
        }
        this._botecoLiberado = true;
        try {
            this._setValue(val);
        } finally {
            this._botecoLiberado = false;
        }
    },
});
