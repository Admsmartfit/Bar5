/** @odoo-module */
// Painel do dono: a noite em tempo real (atualiza sozinho a cada 30 s), metas do plano e alertas.
import { Component, onMounted, onWillStart, onWillUnmount, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { rpc } from "@web/core/network/rpc";

const ATUALIZAR_MS = 30000;

export class PainelDono extends Component {
    static template = "boteco_painel.PainelDono";
    static props = ["*"];

    setup() {
        this.action = useService("action");
        this.state = useState({ d: null, erro: null, carregando: true });
        onWillStart(() => this.carregar());
        let timer = null;
        onMounted(() => (timer = setInterval(() => this.carregar(), ATUALIZAR_MS)));
        onWillUnmount(() => clearInterval(timer));
    }

    async carregar() {
        try {
            const dados = await rpc("/boteco/painel/dados", {}, { silent: true });
            if (dados.erro) {
                this.state.erro = dados.erro;
            } else {
                this.state.d = dados;
                this.state.erro = null;
            }
        } catch {
            this.state.erro = "Sem conexão com o servidor – tentando de novo.";
        } finally {
            this.state.carregando = false;
        }
    }

    reais(valor) {
        return (valor || 0).toLocaleString("pt-BR", { style: "currency", currency: "BRL" });
    }

    variacao(v) {
        if (v === null || v === undefined) {
            return "";
        }
        return `${v > 0 ? "▲" : v < 0 ? "▼" : "="} ${Math.abs(v).toLocaleString("pt-BR")}% vs. semana passada`;
    }

    pctMeta(meta) {
        return meta.meta ? Math.min(100, Math.round((meta.valor * 100) / meta.meta)) : 0;
    }

    abrir(xmlid) {
        this.action.doAction(xmlid);
    }
}

registry.category("actions").add("boteco_painel.painel", PainelDono);
