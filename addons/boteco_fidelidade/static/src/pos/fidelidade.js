/** @odoo-module */
/*
 * Fidelidade do boteco no PDV (Etapa 31), sobre o pos_loyalty gratuito:
 *  - o prêmio de programas com "Resgatar sozinho" entra sozinho quando o cliente completa os pontos
 *    (o Odoo só faz isso para promoções sem cliente; cartão fidelidade pedia um toque no botão);
 *  - happy hour e oferta relâmpago não somam pontos (a menos que a Central de Recursos permita);
 *  - consumo de funcionário não ganha nem usa fidelidade (o servidor confere de novo).
 */
import { patch } from "@web/core/utils/patch";
import { PosOrder } from "@point_of_sale/app/models/pos_order";
import { PosStore } from "@point_of_sale/app/store/pos_store";

patch(PosOrder.prototype, {
    isLineValidForLoyaltyPoints(line) {
        if (this.boteco_tipo_conta === "funcionario") {
            return false;
        }
        // Linha já gravada: o servidor diz a origem do preço; linha nova: o preço promocional do momento
        const origem = line.boteco_preco_origem;
        const produto = line.product_id;
        const promo = origem
            ? ["happy", "oferta"].includes(origem)
            : Boolean(!line.is_reward_line && (produto?.botecoOferta || produto?.botecoEmHappyHour));
        if (promo && !this.botecoFidelidadeComPromocao) {
            return false;
        }
        return super.isLineValidForLoyaltyPoints(...arguments);
    },

    _programIsApplicable(program) {
        if (this.boteco_tipo_conta === "funcionario") {
            return false;
        }
        return super._programIsApplicable(...arguments);
    },
});

patch(PosStore.prototype, {
    async orderUpdateLoyaltyPrograms() {
        const order = this.get_order();
        if (order) {
            // A flag da Central de Recursos vai para o pedido (o modelo do pedido não enxerga o store)
            order.botecoFidelidadeComPromocao = this.botecoRecurso?.("fidelidade_com_promocao");
        }
        await super.orderUpdateLoyaltyPrograms(...arguments);
        if (!order || order.finalized || order.boteco_tipo_conta === "funcionario" || this._botecoResgatando) {
            return;
        }
        const jaNaConta = new Set(order._get_reward_lines().map((l) => l.reward_id?.id));
        const resgatar = order
            .getClaimableRewards(false, false, true)
            .filter(
                ({ reward }) =>
                    reward.program_id.boteco_auto_resgate &&
                    reward.program_id.program_type === "loyalty" &&
                    reward.reward_type === "product" &&
                    !reward.multi_product &&
                    !jaNaConta.has(reward.id)
            );
        if (!resgatar.length) {
            return;
        }
        this._botecoResgatando = true;
        try {
            for (const { reward, coupon_id } of resgatar) {
                order._applyReward(reward, coupon_id);
            }
            await super.orderUpdateLoyaltyPrograms(...arguments);
        } finally {
            this._botecoResgatando = false;
        }
    },
});
