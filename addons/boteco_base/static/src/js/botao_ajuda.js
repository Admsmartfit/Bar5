/** @odoo-module **/
// Botões "?" (ajuda do perfil) e "Trocar de pessoa" na barra superior do Odoo.

import { Component } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";

export class BotecoBotoesSystray extends Component {
    static template = "boteco_base.BotoesSystray";
    static props = {};

    setup() {
        this.ajuda = useService("boteco_ajuda");
    }

    abrirAjuda() {
        // Ajuda rápida (Etapa 26); com o recurso desligado, abre o guia antigo do perfil
        this.ajuda.abrir();
    }

    trocarPessoa() {
        window.location.assign("/boteco/sair");
    }
}

registry.category("systray").add("boteco_base.botoes", { Component: BotecoBotoesSystray }, { sequence: 1 });
