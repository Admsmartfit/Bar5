/** @odoo-module **/
// Aparência do sistema: tema claro/escuro/automático, alto contraste, tamanho da letra e cor de destaque.
// Muda na hora (sem recarregar) e fica salvo no usuário: cada pessoa escolhe a sua.

import { Component, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { session } from "@web/session";
import { user } from "@web/core/user";
import { useService } from "@web/core/utils/hooks";
import { Dropdown } from "@web/core/dropdown/dropdown";

export const PADRAO = { tema: "claro", alto_contraste: true, fonte: "normal", cor: "roxo" };
export const CORES = [
    { codigo: "roxo", nome: "Roxo", hex: "#714b67" },
    { codigo: "azul", nome: "Azul", hex: "#1d4ed8" },
    { codigo: "verde", nome: "Verde", hex: "#15803d" },
    { codigo: "laranja", nome: "Laranja", hex: "#c2410c" },
    { codigo: "grafite", nome: "Grafite", hex: "#374151" },
];

const sistemaEscuro = window.matchMedia ? window.matchMedia("(prefers-color-scheme: dark)") : null;
let atual = { ...PADRAO, ...(session.boteco_aparencia || {}) };

function definir(nome, ligado, valor = "") {
    const raiz = document.documentElement;
    if (ligado) {
        raiz.setAttribute(nome, valor);
    } else {
        raiz.removeAttribute(nome);
    }
}

/** Aplica no <html> (o CSS em boteco_aparencia.scss faz o resto). */
export function aplicarAparencia(preferencias) {
    atual = { ...PADRAO, ...preferencias };
    const escuro = atual.tema === "escuro" || (atual.tema === "auto" && Boolean(sistemaEscuro?.matches));
    definir("data-bt-escuro", escuro);
    definir("data-bt-contraste", atual.alto_contraste);
    definir("data-bt-fonte", atual.fonte !== "normal", atual.fonte);
    definir("data-bt-cor", atual.cor !== "roxo", atual.cor);
}

// Aplica já ao carregar os scripts, antes de desenhar a tela (evita piscar)
aplicarAparencia(atual);
sistemaEscuro?.addEventListener?.("change", () => atual.tema === "auto" && aplicarAparencia(atual));

export class BotecoAparencia extends Component {
    static template = "boteco_base.Aparencia";
    static components = { Dropdown };
    static props = {};

    setup() {
        this.orm = useService("orm");
        this.state = useState({ ...atual });
        this.cores = CORES;
        this.temas = [
            { codigo: "claro", nome: "Claro", icone: "fa-sun-o" },
            { codigo: "escuro", nome: "Escuro", icone: "fa-moon-o" },
            { codigo: "auto", nome: "Automático", icone: "fa-desktop" },
        ];
        this.fontes = [
            { codigo: "normal", nome: "A" },
            { codigo: "grande", nome: "A+" },
            { codigo: "maior", nome: "A++" },
        ];
    }

    get icone() {
        return document.documentElement.hasAttribute("data-bt-escuro") ? "fa-moon-o" : "fa-sun-o";
    }

    async mudar(campo, valor) {
        this.state[campo] = valor;
        aplicarAparencia({ ...this.state });
        const nomes = { tema: "boteco_tema", alto_contraste: "boteco_alto_contraste", fonte: "boteco_tamanho_fonte",
                        cor: "boteco_cor_destaque" };
        try {
            await this.orm.write("res.users", [user.userId], { [nomes[campo]]: valor });
        } catch {
            // Sem rede: a mudança vale nesta tela e é salva na próxima vez
        }
    }
}

registry.category("systray").add("boteco_base.aparencia", { Component: BotecoAparencia }, { sequence: 2 });
