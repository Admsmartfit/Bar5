/** @odoo-module */
// PDV do garçom: aviso de "pronto" (som + notificação) e lista "Prontos para entregar".
import { Component, useState, onWillStart } from "@odoo/owl";
import { patch } from "@web/core/utils/patch";
import { _t } from "@web/core/l10n/translation";
import { Dialog } from "@web/core/dialog/dialog";
import { PosStore } from "@point_of_sale/app/store/pos_store";
import { Navbar } from "@point_of_sale/app/navbar/navbar";
import { usePos } from "@point_of_sale/app/store/pos_hook";
import { tocarSom } from "@boteco_pos/app/utils";

export class ProntosPopup extends Component {
    static template = "boteco_kds.ProntosPopup";
    static components = { Dialog };
    static props = { close: Function };

    setup() {
        this.pos = usePos();
        this.state = useState({ tickets: [], carregando: true });
        onWillStart(() => this.carregar());
    }

    async carregar() {
        this.state.tickets = await this.pos.data.call("boteco.kds.pedido", "kds_prontos_para_entregar", []);
        this.state.carregando = false;
        this.pos.botecoProntos.quantidade = this.state.tickets.length;
    }

    async entregar(ticket) {
        await this.pos.data.call("boteco.kds.pedido", "kds_entregar", [[ticket.id]]);
        this.state.tickets = this.state.tickets.filter((t) => t.id !== ticket.id);
        this.pos.botecoProntos.quantidade = this.state.tickets.length;
    }
}

patch(PosStore.prototype, {
    async setup() {
        await super.setup(...arguments);
        this.botecoProntos = { quantidade: 0 };
        this.data.connectWebSocket("BOTECO_PRONTO", (dados) => this.botecoAoFicarPronto(dados));
        this.data.connectWebSocket("BOTECO_ALERTA", (dados) =>
            this.notification.add(dados.mensagem, { type: "danger", sticky: true })
        );
    },

    botecoAoFicarPronto(dados) {
        this.botecoProntos.quantidade = (this.botecoProntos.quantidade || 0) + 1;
        const meu = !dados.garcom_id || dados.garcom_id === this.user?.id;
        if (meu) {
            tocarSom("bell");
            if (navigator.vibrate) {
                navigator.vibrate([200, 100, 200]);
            }
        }
        this.notification.add(`${dados.mesa}: ${dados.itens.join(", ")}`, {
            title: _t("Pronto para entregar (%s)", dados.setor),
            type: "success",
            sticky: false,
        });
    },

    botecoAbrirProntos() {
        this.dialog.add(ProntosPopup, {});
    },
});

patch(Navbar.prototype, {
    get botecoQtdProntos() {
        return this.pos.botecoProntos?.quantidade || 0;
    },
});
