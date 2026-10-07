/** @odoo-module **/
// Botões "?" (ajuda do perfil) e "Trocar de pessoa" na barra superior do Odoo.

import { Component } from "@odoo/owl";
import { registry } from "@web/core/registry";

export class BotecoBotoesSystray extends Component {
    static template = "boteco_base.BotoesSystray";
    static props = {};

    abrirAjuda() {
        window.open("/boteco/ajuda", "_blank", "noopener");
    }

    trocarPessoa() {
        window.location.assign("/boteco/sair");
    }
}

registry.category("systray").add("boteco_base.botoes", { Component: BotecoBotoesSystray }, { sequence: 1 });
