/** @odoo-module */
// Pagamento: dividir em partes iguais, várias formas e pessoas, CPF/CNPJ na nota.
import { patch } from "@web/core/utils/patch";
import { _t } from "@web/core/l10n/translation";
import { PaymentScreen } from "@point_of_sale/app/screens/payment_screen/payment_screen";
import { makeAwaitable } from "@point_of_sale/app/store/make_awaitable_dialog";
import { NumberPopup } from "@point_of_sale/app/utils/input_popups/number_popup";
import { TextInputPopup } from "@point_of_sale/app/utils/input_popups/text_input_popup";
import { AlertDialog } from "@web/core/confirmation_dialog/confirmation_dialog";
import { dividirEmPartes, documentoValido, soDigitos } from "@boteco_pos/app/utils";

patch(PaymentScreen.prototype, {
    get botecoPartes() {
        return this.currentOrder?.uiState?.botecoPartes || 0;
    },
    get botecoValoresPartes() {
        const n = this.botecoPartes;
        return n > 1 ? dividirEmPartes(this.currentOrder.get_total_with_tax(), n) : [];
    },

    async botecoDividirIgual() {
        const order = this.currentOrder;
        const sugestao = order.getCustomerCount?.() || order.customer_count || 2;
        const valor = await makeAwaitable(this.dialog, NumberPopup, {
            title: _t("Dividir igual entre quantas pessoas?"),
            startingValue: sugestao,
            feedback: (buffer) => {
                const n = parseInt(buffer, 10);
                return n > 1
                    ? _t("%s cada", this.env.utils.formatCurrency(dividirEmPartes(order.get_total_with_tax(), n)[0]))
                    : "";
            },
        });
        const n = parseInt(valor, 10);
        if (!n || n < 2) {
            order.uiState.botecoPartes = 0;
            return;
        }
        order.uiState.botecoPartes = n;
    },

    async addNewPaymentLine(paymentMethod) {
        const resultado = await super.addNewPaymentLine(...arguments);
        const n = this.botecoPartes;
        if (resultado && n > 1) {
            const linhas = this.paymentLines;
            const nova = linhas.at(-1);
            const indice = linhas.length - 1;
            const restante = this.currentOrder.get_due() + nova.amount;
            // As primeiras pessoas pagam a parte delas; a última paga o que faltar (sem sobrar centavo)
            const valor = indice < n - 1 ? Math.min(this.botecoValoresPartes[indice], restante) : restante;
            nova.set_amount(Math.round(valor * 100) / 100);
        }
        return resultado;
    },

    async botecoCpfNaNota() {
        const order = this.currentOrder;
        const texto = await makeAwaitable(this.dialog, TextInputPopup, {
            title: _t("CPF ou CNPJ na nota"),
            placeholder: "000.000.000-00",
            startingValue: order.boteco_cpf_nota || "",
        });
        if (texto === undefined || texto === null) {
            return;
        }
        const digitos = soDigitos(texto);
        if (!digitos) {
            order.update({ boteco_cpf_nota: false });
            return;
        }
        if (!documentoValido(digitos)) {
            this.dialog.add(AlertDialog, {
                title: _t("Documento inválido"),
                body: _t("Confira os números do CPF (11) ou CNPJ (14) e tente de novo."),
            });
            return;
        }
        order.update({ boteco_cpf_nota: digitos });
    },
});
