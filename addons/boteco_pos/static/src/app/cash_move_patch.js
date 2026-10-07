/** @odoo-module */
// Sangria e reforço: motivo obrigatório; sem permissão, PIN do gerente (o servidor confere de novo).
import { patch } from "@web/core/utils/patch";
import { _t } from "@web/core/l10n/translation";
import { CashMovePopup } from "@point_of_sale/app/navbar/cash_move_popup/cash_move_popup";
import { pedirAutorizacao, botecoPode } from "@boteco_pos/app/autorizacao_popup";

patch(CashMovePopup.prototype, {
    async confirm() {
        this._botecoAutorizacaoId = null;
        if (!botecoPode(this.pos, "pode_sangria_reforco")) {
            const aut = await pedirAutorizacao(this.pos, {
                permissao: "pode_sangria_reforco",
                titulo: this.state.type === "in" ? _t("Reforço de caixa") : _t("Sangria"),
                subtitulo: this.state.reason,
                exigirMotivo: false,
                valor: parseFloat(this.state.amount) || 0,
            });
            if (!aut) {
                return;
            }
            this._botecoAutorizacaoId = aut.id;
        }
        return super.confirm(...arguments);
    },

    _prepare_try_cash_in_out_payload(type, amount, reason, extras) {
        const payload = super._prepare_try_cash_in_out_payload(...arguments);
        if (this._botecoAutorizacaoId) {
            payload[4] = { ...payload[4], boteco_autorizacao_id: this._botecoAutorizacaoId };
        }
        return payload;
    },
});
