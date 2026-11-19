/** @odoo-module **/
// Primeiros passos (Etapa 33): assistente curto na 1ª entrada do dono + lista persistente que se marca sozinha.

import { Component, onWillStart, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";

export class PrimeirosPassos extends Component {
    static template = "boteco_base.PrimeirosPassos";
    static props = ["*"];

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.ajuda = useService("boteco_ajuda");
        this.notification = useService("notification");
        this.state = useState({ dados: null, telaAssistente: 1, empresa: {}, ocupado: false });
        onWillStart(() => this.carregar());
    }

    async carregar() {
        const dados = await this.orm.call("boteco.implantacao", "estado", []);
        this.state.dados = dados;
        this.state.empresa = { ...dados.empresa };
    }

    get progresso() {
        const d = this.state.dados;
        return d && d.total ? Math.round((d.feitos / d.total) * 100) : 0;
    }

    icone(passo) {
        return { feito: "fa-check-circle text-success", pulado: "fa-forward text-muted" }[passo.situacao] ||
            (passo.obrigatorio ? "fa-circle-o text-warning" : "fa-circle-o text-muted");
    }

    // ---------------------------------------------------------------- assistente (3 telas)
    proximaTela() {
        this.state.telaAssistente++;
    }

    voltarTela() {
        this.state.telaAssistente = Math.max(1, this.state.telaAssistente - 1);
    }

    async concluirAssistente() {
        this.state.ocupado = true;
        try {
            this.state.dados = await this.orm.call("boteco.implantacao", "salvar_assistente", [this.state.empresa]);
        } finally {
            this.state.ocupado = false;
        }
    }

    // ---------------------------------------------------------------- lista
    async fazer(passo) {
        const acao = await this.orm.call("boteco.implantacao", "acao", [passo.codigo]);
        await this.action.doAction(acao);
    }

    verAjuda(passo) {
        this.ajuda.abrirArtigo(passo.artigo);
    }

    async marcar(passo, situacao) {
        this.state.dados = await this.orm.call("boteco.implantacao", "marcar", [passo.codigo, situacao]);
    }

    async abrirCasa() {
        const d = this.state.dados;
        let forcar = false;
        if (d.faltam) {
            forcar = window.confirm(
                `Ainda faltam ${d.faltam} passo(s) obrigatório(s). Abrir a casa mesmo assim? (fica registrado na auditoria)`
            );
            if (!forcar) {
                return;
            }
        }
        await this.orm.call("boteco.implantacao", "concluir", [forcar]);
        this.notification.add("Casa aberta! 🎉 Bom trabalho. A lista continua em Início › Primeiros passos.", {
            type: "success",
        });
        await this.carregar();
    }
}

registry.category("actions").add("boteco_base.primeiros_passos", PrimeirosPassos);
