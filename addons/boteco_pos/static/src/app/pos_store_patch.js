/** @odoo-module */
import { patch } from "@web/core/utils/patch";
import { _t } from "@web/core/l10n/translation";
import { PosStore } from "@point_of_sale/app/store/pos_store";
import { pedirAutorizacao } from "@boteco_pos/app/autorizacao_popup";
import { qtdEnviada, tocarSom } from "@boteco_pos/app/utils";

function arredondar(valor) {
    return Math.round(valor * 100) / 100;
}

patch(PosStore.prototype, {
    async setup() {
        await super.setup(...arguments);
        this.data.connectWebSocket("BOTECO_MESA", (dados) => this.botecoAoMudarMesa(dados));
    },

    get botecoDados() {
        return this.session?._boteco || {};
    },

    // ------------------------------------------------------------------
    // Mesas: "chamou garçom" / "pediu a conta" chegam em tempo real
    // ------------------------------------------------------------------
    botecoAoMudarMesa(dados) {
        const mesa = this.models["restaurant.table"]?.get(dados.id);
        if (!mesa) {
            return;
        }
        mesa.update({
            boteco_chamou_garcom: dados.boteco_chamou_garcom,
            boteco_chamou_garcom_em: dados.boteco_chamou_garcom_em,
            boteco_pediu_conta: dados.boteco_pediu_conta,
            boteco_pediu_conta_em: dados.boteco_pediu_conta_em,
        });
        if (dados.evento === "pediu_conta") {
            tocarSom("bell");
            this.notification.add(_t("Mesa %s pediu a conta", dados.numero), { type: "warning", sticky: false });
        } else if (dados.evento === "chamou_garcom") {
            tocarSom("bell");
            this.notification.add(_t("Mesa %s chamou o garçom", dados.numero), { type: "info", sticky: false });
        }
    },

    async botecoMarcarAtendido(mesa) {
        await this.data.call("restaurant.table", "boteco_marcar", [[mesa.id]], { chamou_garcom: false });
    },

    // ------------------------------------------------------------------
    // Taxa de serviço e couvert
    // ------------------------------------------------------------------
    botecoProdutoTaxa() {
        const id = this.botecoDados.produto_taxa_id;
        return id ? this.models["product.product"].get(id) : null;
    },
    botecoProdutoCouvert() {
        const id = this.botecoDados.produto_couvert_id;
        return id ? this.models["product.product"].get(id) : null;
    },
    botecoLinhasServico(order) {
        const taxa = this.botecoProdutoTaxa();
        const couvert = this.botecoProdutoCouvert();
        return {
            taxa: taxa ? order.lines.find((l) => l.product_id?.id === taxa.id) : null,
            couvert: couvert ? order.lines.find((l) => l.product_id?.id === couvert.id) : null,
        };
    },
    botecoTaxaAplicavel(order) {
        const d = this.botecoDados;
        return Boolean(
            order &&
                d.taxa_pct > 0 &&
                d.produto_taxa_id &&
                (order.table_id || d.taxa_no_balcao) &&
                !order.boteco_taxa_removida &&
                order.boteco_tipo_conta !== "funcionario"
        );
    },
    /** Base da taxa: consumo, sem a própria taxa e sem couvert. */
    botecoBaseTaxa(order) {
        const ignorar = [this.botecoProdutoTaxa()?.id, this.botecoProdutoCouvert()?.id];
        return order.lines
            .filter((l) => !ignorar.includes(l.product_id?.id))
            .reduce((total, l) => total + l.get_price_with_tax(), 0);
    },
    botecoValorTaxa(order) {
        if (!this.botecoTaxaAplicavel(order)) {
            return 0;
        }
        return arredondar((this.botecoBaseTaxa(order) * this.botecoDados.taxa_pct) / 100);
    },
    async botecoAtualizarTaxa(order) {
        const { taxa: linha } = this.botecoLinhasServico(order);
        const valor = this.botecoValorTaxa(order);
        if (valor <= 0) {
            if (linha) {
                order.removeOrderline(linha);
            }
            return;
        }
        if (linha) {
            linha.set_unit_price(valor);
            linha.set_quantity(1, true);
        } else {
            await this.addLineToOrder(
                { product_id: this.botecoProdutoTaxa(), qty: 1, price_unit: valor, skip_change: true },
                order,
                {},
                false
            );
        }
    },
    botecoCouvertAplicavel(order) {
        const d = this.botecoDados;
        return Boolean(
            order && d.couvert_valor > 0 && d.produto_couvert_id && order.table_id &&
                !order.boteco_couvert_removido && order.boteco_tipo_conta !== "funcionario"
        );
    },
    async botecoAtualizarCouvert(order) {
        const { couvert: linha } = this.botecoLinhasServico(order);
        if (!this.botecoCouvertAplicavel(order)) {
            if (linha) {
                order.removeOrderline(linha);
            }
            return;
        }
        const pessoas = Math.max(order.getCustomerCount?.() || order.customer_count || 1, 1);
        if (linha) {
            linha.set_unit_price(this.botecoDados.couvert_valor);
            linha.set_quantity(pessoas, true);
        } else {
            await this.addLineToOrder(
                {
                    product_id: this.botecoProdutoCouvert(),
                    qty: pessoas,
                    price_unit: this.botecoDados.couvert_valor,
                    skip_change: true,
                },
                order,
                {},
                false
            );
        }
    },
    async botecoPrepararConta(order) {
        if (!order || order.finalized) {
            return;
        }
        await this.botecoAtualizarCouvert(order);
        await this.botecoAtualizarTaxa(order);
    },

    async botecoTirarServico(order, tipo) {
        const ehTaxa = tipo === "taxa";
        const linhas = this.botecoLinhasServico(order);
        const valor = ehTaxa ? this.botecoValorTaxa(order) : linhas.couvert?.get_price_with_tax() || 0;
        const aut = await pedirAutorizacao(this, {
            permissao: "pode_remover_taxa",
            titulo: ehTaxa ? _t("Tirar a taxa de serviço") : _t("Tirar o couvert"),
            tipoMotivo: "taxa",
            referencia: order.uuid,
            valor,
        });
        if (!aut) {
            return false;
        }
        order.update(ehTaxa ? { boteco_taxa_removida: true } : { boteco_couvert_removido: true });
        const linha = ehTaxa ? linhas.taxa : linhas.couvert;
        if (linha) {
            order.removeOrderline(linha);
        }
        await this.data.call("pos.session", "boteco_registrar_acao", [ehTaxa ? "remover_taxa" : "remover_couvert", {
            permissao: "pode_remover_taxa",
            autorizacao_id: aut.id,
            referencia: order.uuid,
            valor,
            motivo: aut.motivo,
            descricao: (ehTaxa ? _t("Taxa retirada") : _t("Couvert retirado")) +
                (order.table_id ? _t(" – mesa %s", order.table_id.table_number) : ""),
        }]);
        return true;
    },

    botecoDevolverServico(order, tipo) {
        order.update(tipo === "taxa" ? { boteco_taxa_removida: false } : { boteco_couvert_removido: false });
        return this.botecoPrepararConta(order);
    },

    async pay() {
        await this.botecoPrepararConta(this.get_order());
        return super.pay(...arguments);
    },

    // ------------------------------------------------------------------
    // Consumo de funcionário: preço de custo ou zero em todas as linhas
    // ------------------------------------------------------------------
    botecoPrecoFuncionario(order, product) {
        return order.boteco_funcionario_modo === "zero" ? 0 : product.standard_price || 0;
    },
    async addLineToOrder(vals, order, opts = {}, configure = true) {
        const linha = await super.addLineToOrder(vals, order, opts, configure);
        if (linha && order?.boteco_tipo_conta === "funcionario") {
            linha.price_type = "manual";
            linha.set_unit_price(this.botecoPrecoFuncionario(order, linha.product_id));
        }
        return linha;
    },

    // ------------------------------------------------------------------
    // Desconto: sempre com motivo; sem permissão, com PIN do gerente
    // ------------------------------------------------------------------
    async setDiscountFromUI(line, val) {
        const novo = parseFloat(val) || 0;
        if (novo > (line.get_discount() || 0) && !line.boteco_cortesia) {
            const aut = await pedirAutorizacao(this, {
                permissao: "pode_dar_desconto",
                titulo: _t("Desconto de %s%% em %s", novo, line.get_full_product_name()),
                tipoMotivo: "desconto",
                referencia: line.uuid,
                valor: (line.get_unit_price() * line.get_quantity() * novo) / 100,
            });
            if (!aut) {
                return;
            }
            line.update({ boteco_motivo: aut.motivo, boteco_autorizacao_ref: aut.id });
        }
        return super.setDiscountFromUI(line, val);
    },

    // ------------------------------------------------------------------
    // Cancelar a conta inteira com itens já enviados: PIN do gerente
    // ------------------------------------------------------------------
    async onDeleteOrder(order) {
        const enviados = order?.lines?.filter((l) => qtdEnviada(order, l) > 0) || [];
        if (enviados.length) {
            const aut = await pedirAutorizacao(this, {
                permissao: "pode_cancelar_item",
                titulo: _t("Cancelar a conta inteira"),
                subtitulo: _t("%s item(ns) já foram para a produção.", enviados.length),
                tipoMotivo: "cancelamento",
                referencia: order.uuid,
                valor: order.get_total_with_tax(),
            });
            if (!aut) {
                return false;
            }
        }
        return super.onDeleteOrder(...arguments);
    },
});
