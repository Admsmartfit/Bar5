/** @odoo-module */
import { patch } from "@web/core/utils/patch";
import { SelfOrder } from "@pos_self_order/app/self_order_service";
import { SincronizadorCardapio } from "@boteco_cardapio/app/estado_cardapio";

patch(SelfOrder.prototype, {
    async setup() {
        await super.setup(...arguments);
        this.botecoSincronizadorCardapio = new SincronizadorCardapio(this, {
            configId: this.config.id,
            accessToken: this.access_token,
            conectar: (canal, callback) => this.data.connectWebSocket(canal, callback),
        });
        this.botecoSincronizadorCardapio.iniciar();
    },

    getProductDisplayPrice(product) {
        void this.botecoCardapio?.versao;
        return super.getProductDisplayPrice(product);
    },
});
