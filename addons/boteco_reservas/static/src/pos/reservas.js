/** @odoo-module */
/*
 * Reservas no mapa do salão (Etapa 27):
 *  - mesa livre com reserva na próxima hora fica "Reservada" (cor própria) com horário, nome e pessoas;
 *  - abrir a mesa reservada marca "Chegou" e já põe o número de pessoas da reserva na conta.
 */
import { reactive } from "@odoo/owl";
import { patch } from "@web/core/utils/patch";
import { _t } from "@web/core/l10n/translation";
import { PosStore } from "@point_of_sale/app/store/pos_store";
import { FloorScreen } from "@pos_restaurant/app/floor_screen/floor_screen";
import { ROTULOS_STATUS } from "@boteco_pos/app/floor_screen_patch";

const ATUALIZAR_MS = 120000;
const JANELA_MIN = 60; // reserva na próxima hora pinta a mesa
ROTULOS_STATUS.reservada = _t("Reservada");

patch(PosStore.prototype, {
    async setup() {
        await super.setup(...arguments);
        this.botecoReservas = reactive({ mapa: {} });
        if (!this.config.module_pos_restaurant) {
            return;
        }
        this.botecoAtualizarReservas();
        setInterval(() => this.botecoAtualizarReservas(), ATUALIZAR_MS);
        this.data.connectWebSocket("BOTECO_RESERVA", () => this.botecoAtualizarReservas());
    },

    async botecoAtualizarReservas() {
        if (!this.botecoRecurso?.("reservas_mesas")) {
            this.botecoReservas.mapa = {};
            return;
        }
        try {
            this.botecoReservas.mapa = await this.data.call("restaurant.table", "boteco_reservas_mapa", [this.config.id]);
        } catch {
            // sem rede: fica o último mapa
        }
    },

    botecoReservaDaMesa(table) {
        return table ? this.botecoReservas?.mapa?.[String(table.id)] || null : null;
    },

    createNewOrder() {
        const order = super.createNewOrder(...arguments);
        const mesa = order?.table_id;
        const reserva = this.botecoReservaDaMesa(mesa);
        if (mesa && reserva && reserva.minutos <= JANELA_MIN) {
            this.data
                .call("restaurant.table", "boteco_reserva_chegou", [[mesa.id]])
                .then((resultado) => {
                    if (resultado) {
                        order.setCustomerCount?.(resultado.pessoas);
                        this.notification.add(_t("Reserva de %s: chegou (%s pessoas).", resultado.nome, resultado.pessoas), {
                            type: "success",
                        });
                        this.botecoAtualizarReservas();
                    }
                })
                .catch(() => {});
        }
        return order;
    },
});

patch(FloorScreen.prototype, {
    botecoReserva(table) {
        const reserva = this.pos.botecoReservaDaMesa(table);
        return reserva && reserva.minutos <= JANELA_MIN ? reserva : null;
    },

    botecoStatusMesa(table) {
        const status = super.botecoStatusMesa(...arguments);
        return status === "livre" && this.botecoReserva(table) ? "reservada" : status;
    },
});
