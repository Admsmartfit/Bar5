/** @odoo-module */
/*
 * Fechamento com contagem cega: o operador digita o que contou em cada forma de pagamento
 * ANTES de ver o esperado. "Conferir" grava a contagem no servidor (com PIN do gerente, se
 * preciso) e só então mostra esperado e diferença por forma de pagamento.
 */
import { patch } from "@web/core/utils/patch";
import { _t } from "@web/core/l10n/translation";
import { ClosePosPopup } from "@point_of_sale/app/navbar/closing_popup/closing_popup";
import { AlertDialog } from "@web/core/confirmation_dialog/confirmation_dialog";
import { parseFloat as parseFloatOdoo } from "@web/views/fields/parsers";
import { pedirAutorizacao } from "@boteco_pos/app/autorizacao_popup";

patch(ClosePosPopup.prototype, {
    get botecoCego() {
        return Boolean(this.pos.session._boteco?.contagem_cega);
    },

    getInitialState() {
        const estado = super.getInitialState(...arguments);
        estado.botecoConferido = false;
        estado.botecoResultado = null;
        if (this.pos.session._boteco?.contagem_cega) {
            for (const chave of Object.keys(estado.payments)) {
                estado.payments[chave].counted = "";
            }
        }
        return estado;
    },

    canConfirm() {
        if (this.botecoCego && !this.state.botecoConferido) {
            return false;
        }
        return super.canConfirm(...arguments);
    },

    botecoPodeConferir() {
        return Object.values(this.state.payments).every(
            (p) => p.counted !== "" && this.env.utils.isValidFloat(p.counted)
        );
    },

    async botecoConferir() {
        if (!this.botecoPodeConferir()) {
            this.dialog.add(AlertDialog, {
                title: _t("Falta contar"),
                body: _t("Digite o valor contado de todas as formas de pagamento (zero se não tiver)."),
            });
            return;
        }
        const aut = await pedirAutorizacao(this.pos, {
            permissao: "pode_abrir_fechar_caixa",
            titulo: _t("Fechar o caixa"),
            exigirMotivo: false,
            referencia: String(this.pos.session.id),
        });
        if (!aut) {
            return;
        }
        const contagens = {};
        for (const [id, pagamento] of Object.entries(this.state.payments)) {
            contagens[id] = parseFloatOdoo(pagamento.counted);
        }
        try {
            const resultado = await this.pos.data.call(
                "pos.session",
                "boteco_registrar_contagem",
                [[this.pos.session.id], contagens],
                { autorizacao_id: aut.id, observacao: this.state.notes || null }
            );
            this.state.botecoResultado = resultado;
            this.state.botecoConferido = true;
        } catch (erro) {
            this.dialog.add(AlertDialog, {
                title: _t("Não deu para fechar"),
                body: erro?.data?.message || _t("Confira a conexão e tente de novo."),
            });
        }
    },
});
