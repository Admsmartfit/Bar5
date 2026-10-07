/** @odoo-module */
import { patch } from "@web/core/utils/patch";
import { PosStore } from "@point_of_sale/app/store/pos_store";
import { SincronizadorCardapio } from "@boteco_cardapio/app/estado_cardapio";

patch(PosStore.prototype, {
    async setup() {
        await super.setup(...arguments);
        this.botecoSincronizadorCardapio = new SincronizadorCardapio(this, {
            configId: this.config.id,
            accessToken: this.config.access_token,
            conectar: (canal, callback) => this.data.connectWebSocket(canal, callback),
        });
        this.botecoSincronizadorCardapio.iniciar();
    },

    getProductPrice(product, p = false) {
        // Lê a versão para a tela redesenhar o preço na virada do happy hour
        void this.botecoCardapio?.versao;
        return super.getProductPrice(product, p);
    },
});
