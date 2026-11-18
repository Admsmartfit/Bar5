/** @odoo-module */
/*
 * Tablet neutro (Etapa 16, flag tablet_neutro_anti_burst):
 *  - a partir da 3ª unidade do mesmo item, o "+" só aceita um toque a cada 350 ms
 *    (evita 10 pratos por dedo nervoso ou criança brincando);
 *  - o número de pessoas da mesa nunca é mostrado nem alterado pelo tablet (o servidor usa o N
 *    que o garçom definiu e ignora o que vier do aparelho).
 */
import { patch } from "@web/core/utils/patch";
import { ProductPage } from "@pos_self_order/app/pages/product_page/product_page";
import { CartPage } from "@pos_self_order/app/pages/cart_page/cart_page";

export const INTERVALO_MS = 350;
export const A_PARTIR_DE = 2; // já tem 2: o toque que levaria à 3ª unidade passa a ter trava

/** true = pode somar agora; false = toque repetido rápido demais (ignorado). */
export function liberarToque(estado, chave, qtdAtual, agora = Date.now()) {
    if (qtdAtual < A_PARTIR_DE) {
        return true;
    }
    const ultimo = estado[chave] || 0;
    if (agora - ultimo < INTERVALO_MS) {
        return false;
    }
    estado[chave] = agora;
    return true;
}

const toques = {};

patch(ProductPage.prototype, {
    changeQuantity(increase) {
        if (
            increase &&
            this.selfOrder.botecoRecurso?.("tablet_neutro_anti_burst") &&
            !liberarToque(toques, `p${this.props.product.id}`, this.state.qty)
        ) {
            return;
        }
        return super.changeQuantity(...arguments);
    },
});

patch(CartPage.prototype, {
    async changeQuantity(line, increase) {
        if (
            increase &&
            this.selfOrder.botecoRecurso?.("tablet_neutro_anti_burst") &&
            !liberarToque(toques, `l${line.uuid}`, line.qty)
        ) {
            return;
        }
        return super.changeQuantity(...arguments);
    },
});
