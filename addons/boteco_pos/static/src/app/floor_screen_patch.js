/** @odoo-module */
/*
 * Mapa de mesas com cor por situação (seção 4 do PRD: cor fixa por status):
 *   livre · ocupada · chamou garçom · pediu a conta (roxo) · esperando pagamento · atrasada (vermelho)
 * e o tempo desde o último pedido em cada mesa.
 */
import { onMounted, onWillUnmount, useState } from "@odoo/owl";
import { patch } from "@web/core/utils/patch";
import { _t } from "@web/core/l10n/translation";
import { FloorScreen } from "@pos_restaurant/app/floor_screen/floor_screen";
import { minutosDesde } from "@boteco_pos/app/utils";

export const ROTULOS_STATUS = {
    livre: _t("Livre"),
    ocupada: _t("Ocupada"),
    chamou: _t("Chamou"),
    conta: _t("Pediu a conta"),
    pagamento: _t("Esperando pagamento"),
    atrasada: _t("Atrasada"),
};

patch(FloorScreen.prototype, {
    setup() {
        super.setup(...arguments);
        this.botecoRelogio = useState({ agora: Date.now() });
        let timer = null;
        onMounted(() => {
            timer = setInterval(() => (this.botecoRelogio.agora = Date.now()), 30000);
        });
        onWillUnmount(() => clearInterval(timer));
    },

    botecoPedidoDaMesa(table) {
        return this.pos.models["pos.order"].find((o) => o.table_id?.id === table.id && !o.finalized);
    },

    botecoMinutosUltimoPedido(table) {
        const pedido = this.botecoPedidoDaMesa(table);
        if (!pedido) {
            return null;
        }
        const enviado = pedido.last_order_preparation_change?.metadata?.serverDate;
        const referencia = enviado || pedido.boteco_ultimo_envio;
        return minutosDesde(referencia, this.botecoRelogio.agora);
    },

    botecoStatusMesa(table) {
        const pedido = this.botecoPedidoDaMesa(table);
        if (table.boteco_pediu_conta) {
            return "conta";
        }
        if (table.boteco_chamou_garcom) {
            return "chamou";
        }
        if (!pedido) {
            return "livre";
        }
        if ((pedido.nb_print || 0) > 0) {
            return "pagamento";
        }
        const limite = this.pos.session._boteco?.minutos_atraso || 30;
        const minutos = this.botecoMinutosUltimoPedido(table);
        if (minutos !== null && minutos >= limite && pedido.lines.length) {
            return "atrasada";
        }
        return "ocupada";
    },

    botecoTempoMesa(table) {
        const minutos = this.botecoMinutosUltimoPedido(table);
        if (minutos === null) {
            return "";
        }
        if (minutos < 60) {
            return `${minutos} min`;
        }
        return `${Math.floor(minutos / 60)}h${String(minutos % 60).padStart(2, "0")}`;
    },

    botecoRotuloStatus(table) {
        return ROTULOS_STATUS[this.botecoStatusMesa(table)] || "";
    },

    async botecoAtender(table, ev) {
        ev?.stopPropagation();
        await this.pos.botecoMarcarAtendido(table);
    },
});
