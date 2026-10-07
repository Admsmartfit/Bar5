/** @odoo-module */
// PDV do garçom: liberar celular do QR (um toque) e conferir idade (+18) da mesa.
import { patch } from "@web/core/utils/patch";
import { _t } from "@web/core/l10n/translation";
import { ConfirmationDialog } from "@web/core/confirmation_dialog/confirmation_dialog";
import { PosStore } from "@point_of_sale/app/store/pos_store";
import { tocarSom } from "@boteco_pos/app/utils";
import { botecoPode } from "@boteco_pos/app/autorizacao_popup";

patch(PosStore.prototype, {
    async setup() {
        await super.setup(...arguments);
        this.botecoDialogosAbertos = new Set();
        this.data.connectWebSocket("BOTECO_APROVAR", (dados) => this.botecoPedirAprovacao(dados));
        this.data.connectWebSocket("BOTECO_MAIOR18", (dados) => this.botecoPedirIdade(dados));
    },

    botecoPedirAprovacao(dados) {
        const chave = `disp-${dados.id}`;
        if (!botecoPode(this, "pode_aprovar_qr") || this.botecoDialogosAbertos.has(chave)) {
            return;
        }
        this.botecoDialogosAbertos.add(chave);
        tocarSom("bell");
        this.dialog.add(
            ConfirmationDialog,
            {
                title: _t("Mesa %s: celular quer pedir", dados.mesa),
                body: _t("Confira se a pessoa está mesmo na mesa %s e libere com um toque.", dados.mesa),
                confirmLabel: _t("Liberar"),
                cancelLabel: _t("Recusar"),
                confirm: () => this.data.call("boteco.dispositivo", "boteco_aprovar", [[dados.id]]),
                cancel: () => this.data.call("boteco.dispositivo", "boteco_recusar", [[dados.id]]),
            },
            { onClose: () => this.botecoDialogosAbertos.delete(chave) }
        );
    },

    botecoPedirIdade(dados) {
        const chave = `idade-${dados.mesa_id}`;
        if (!botecoPode(this, "pode_aprovar_qr") || this.botecoDialogosAbertos.has(chave)) {
            return;
        }
        this.botecoDialogosAbertos.add(chave);
        tocarSom("bell");
        this.dialog.add(
            ConfirmationDialog,
            {
                title: _t("Mesa %s: bebida alcoólica (+18)", dados.mesa),
                body: _t(
                    "Primeira bebida alcoólica da mesa. Confira a idade de quem vai beber. " +
                        "O pedido só vai para o bar depois da sua confirmação."
                ),
                confirmLabel: _t("Todos têm 18+"),
                cancelLabel: _t("Depois"),
                confirm: () => this.data.call("restaurant.table", "boteco_confirmar_maior18", [[dados.mesa_id]]),
                cancel: () => {},
            },
            { onClose: () => this.botecoDialogosAbertos.delete(chave) }
        );
    },
});
