/** @odoo-module */
// Caixa "Primeiros passos" em destaque na barra de cima (só o dono). Some quando a implantação termina.
import { Component, onWillStart, onMounted, onWillUnmount, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";

export class SystrayPrimeirosPassos extends Component {
    static template = "boteco_base.SystrayPrimeirosPassos";
    static props = {};

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.state = useState({ mostrar: false, feitos: 0, total: 0, faltam: 0 });
        onWillStart(() => this.atualizar());
        let timer = null;
        onMounted(() => (timer = setInterval(() => this.atualizar(), 60000)));
        onWillUnmount(() => clearInterval(timer));
    }

    async atualizar() {
        try {
            Object.assign(this.state, await this.orm.call("boteco.implantacao", "resumo", [], {}, { silent: true }));
        } catch {
            this.state.mostrar = false;
        }
    }

    get pct() {
        return this.state.total ? Math.round((this.state.feitos / this.state.total) * 100) : 0;
    }

    abrir() {
        this.action.doAction("boteco_base.action_boteco_primeiros_passos");
    }
}

registry.category("systray").add("boteco_base.primeiros_passos", { Component: SystrayPrimeirosPassos }, { sequence: 100 });
