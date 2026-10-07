/** @odoo-module */
// Botões do boteco em "Ações": cortesia, consumo de funcionário, taxa e couvert.
import { patch } from "@web/core/utils/patch";
import { _t } from "@web/core/l10n/translation";
import { ControlButtons } from "@point_of_sale/app/screens/product_screen/control_buttons/control_buttons";
import { makeAwaitable } from "@point_of_sale/app/store/make_awaitable_dialog";
import { SelectionPopup } from "@point_of_sale/app/utils/input_popups/selection_popup";
import { AlertDialog } from "@web/core/confirmation_dialog/confirmation_dialog";
import { pedirAutorizacao } from "@boteco_pos/app/autorizacao_popup";

patch(ControlButtons.prototype, {
    get botecoTaxaValor() {
        return this.pos.botecoValorTaxa(this.currentOrder);
    },
    get botecoTemTaxa() {
        const order = this.currentOrder;
        return Boolean(order && this.pos.botecoDados.taxa_pct > 0 && (order.table_id || this.pos.botecoDados.taxa_no_balcao));
    },
    get botecoTemCouvert() {
        return Boolean(this.currentOrder?.table_id && this.pos.botecoDados.couvert_valor > 0);
    },

    async clickBotecoCortesia() {
        const linha = this.currentOrder?.get_selected_orderline();
        if (!linha) {
            this.dialog.add(AlertDialog, {
                title: _t("Escolha o item"),
                body: _t("Toque no item da conta que vai ser cortesia e depois em Cortesia."),
            });
            return;
        }
        const aut = await pedirAutorizacao(this.pos, {
            permissao: "pode_dar_cortesia",
            titulo: _t("Cortesia: %s x %s", linha.get_quantity(), linha.get_full_product_name()),
            tipoMotivo: "cortesia",
            referencia: linha.uuid,
            valor: linha.get_unit_price() * linha.get_quantity(),
        });
        if (!aut) {
            return;
        }
        linha.update({ boteco_cortesia: true, boteco_motivo: aut.motivo, boteco_autorizacao_ref: aut.id });
        linha.set_discount(100);
        this.props.close?.();
    },

    async clickBotecoFuncionario() {
        const order = this.currentOrder;
        if (!order) {
            return;
        }
        const funcionarios = this.pos.botecoDados.funcionarios || [];
        const pessoa = await makeAwaitable(this.dialog, SelectionPopup, {
            title: _t("Consumo de quem?"),
            list: funcionarios.map((f) => ({ id: f.id, label: f.nome, item: f })),
        });
        if (!pessoa) {
            return;
        }
        const modo = await makeAwaitable(this.dialog, SelectionPopup, {
            title: _t("Como cobrar?"),
            list: [
                { id: 1, label: _t("A preço de custo"), item: "custo" },
                { id: 2, label: _t("Sem cobrar (zero)"), item: "zero" },
            ],
        });
        if (!modo) {
            return;
        }
        const aut = await pedirAutorizacao(this.pos, {
            permissao: "pode_consumo_funcionario",
            titulo: _t("Consumo de %s", pessoa.nome),
            exigirMotivo: false,
            referencia: order.uuid,
        });
        if (!aut) {
            return;
        }
        order.update({
            boteco_tipo_conta: "funcionario",
            boteco_funcionario_ref: pessoa.id,
            boteco_funcionario_modo: modo,
            boteco_autorizacao_ref: aut.id,
            boteco_taxa_removida: true,
        });
        for (const linha of [...order.lines]) {
            const { taxa, couvert } = this.pos.botecoLinhasServico(order);
            if (linha === taxa || linha === couvert) {
                order.removeOrderline(linha);
                continue;
            }
            linha.price_type = "manual";
            linha.set_unit_price(this.pos.botecoPrecoFuncionario(order, linha.product_id));
        }
        this.props.close?.();
    },

    async clickBotecoTaxa() {
        const order = this.currentOrder;
        if (order.boteco_taxa_removida) {
            await this.pos.botecoDevolverServico(order, "taxa");
        } else {
            await this.pos.botecoTirarServico(order, "taxa");
        }
        this.props.close?.();
    },

    async clickBotecoCouvert() {
        const order = this.currentOrder;
        if (order.boteco_couvert_removido) {
            await this.pos.botecoDevolverServico(order, "couvert");
        } else {
            await this.pos.botecoTirarServico(order, "couvert");
        }
        this.props.close?.();
    },

    async clickPrintBill() {
        // Pré-conta já com couvert e taxa de serviço
        await this.pos.botecoPrepararConta(this.currentOrder);
        return super.clickPrintBill(...arguments);
    },
});
