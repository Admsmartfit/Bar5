/** @odoo-module */
// Botão "Pendências" na barra do PDV e a lista (aberta só quando o garçom quer: não interrompe o pedido).
import { Component, onMounted, onWillUnmount, useState } from "@odoo/owl";
import { patch } from "@web/core/utils/patch";
import { Dialog } from "@web/core/dialog/dialog";
import { usePos } from "@point_of_sale/app/store/pos_hook";
import { Navbar } from "@point_of_sale/app/navbar/navbar";

export class BotecoPendenciasDialog extends Component {
    static template = "boteco_autoatendimento.PendenciasDialog";
    static components = { Dialog };
    static props = ["close"];

    setup() {
        this.pos = usePos();
        this.relogio = useState({ agora: Date.now() });
        let timer = null;
        onMounted(() => (timer = setInterval(() => (this.relogio.agora = Date.now()), 15000)));
        onWillUnmount(() => clearInterval(timer));
    }

    get itens() {
        return [...this.pos.botecoPendencias.itens].sort((a, b) => a.desde - b.desde);
    }

    espera(item) {
        const min = Math.floor((this.relogio.agora - item.desde) / 60000);
        return min < 1 ? "agora" : `há ${min} min`;
    }

    resolver(item) {
        this.props.close();
        this.pos.botecoResolver(item.chave);
    }
}

patch(Navbar.prototype, {
    get botecoQtdPendencias() {
        return this.pos.botecoPendencias?.itens.length || 0;
    },
    get botecoPendenciaAntiga() {
        return (this.pos.botecoPendencias?.itens || []).some((i) => Date.now() - i.desde > 30000);
    },
    botecoAbrirPendencias() {
        this.dialog.add(BotecoPendenciasDialog, {});
    },
});
