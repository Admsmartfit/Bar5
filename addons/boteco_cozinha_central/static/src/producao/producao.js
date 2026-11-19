/** @odoo-module */
/*
 * Tela de produção da cozinha central (tablet): "Iniciar", "Pesar", "Finalizar".
 * O único dado digitado é o peso (teclado numérico grande na própria tela).
 */
import { Component, onWillStart, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { _t } from "@web/core/l10n/translation";

export class TelaProducao extends Component {
    static template = "boteco_cozinha.TelaProducao";
    static props = ["*"];

    setup() {
        this.orm = useService("orm");
        this.notification = useService("notification");
        this.state = useState({ producoes: [], aberta: null, peso: "", resultado: null, enviando: false,
                                faltas: null, erroPin: "", pinGerente: "" });
        this.teclas = ["1", "2", "3", "4", "5", "6", "7", "8", "9", ",", "0", "apagar"];
        onWillStart(() => this.carregar());
    }

    async carregar() {
        this.state.producoes = await this.orm.call("mrp.production", "boteco_dados_tela", []);
        if (this.state.aberta) {
            this.state.aberta = this.state.producoes.find((p) => p.id === this.state.aberta.id) || null;
        }
    }

    abrir(producao) {
        this.state.aberta = producao;
        this.state.peso = "";
        this.state.resultado = null;
    }

    voltar() {
        this.state.aberta = null;
        this.state.resultado = null;
        this.carregar();
    }

    async iniciar() {
        const [dados] = await this.orm.call("mrp.production", "boteco_iniciar", [[this.state.aberta.id]]);
        this.state.aberta = dados;
    }

    tecla(t) {
        if (t === "apagar") {
            this.state.peso = this.state.peso.slice(0, -1);
        } else if (t === ",") {
            if (!this.state.peso.includes(",")) {
                this.state.peso = (this.state.peso || "0") + ",";
            }
        } else if (this.state.peso.length < 7) {
            this.state.peso += t;
        }
    }

    get pesoNumero() {
        return parseFloat((this.state.peso || "").replace(",", "."));
    }

    async finalizar() {
        if (!(this.pesoNumero > 0) || this.state.enviando) {
            this.notification.add(_t("Digite o peso que saiu na balança."), { type: "warning" });
            return;
        }
        this.state.enviando = true;
        try {
            const r = await this.orm.call("mrp.production", "boteco_finalizar", [
                [this.state.aberta.id],
                this.pesoNumero,
                this.state.pinGerente || null,
            ]);
            if (r && r.precisa_pin) {
                // Insumo sem saldo: mostra o que falta e pede o PIN do gerente (fica na auditoria)
                this.state.faltas = r.faltas;
                this.state.erroPin = r.erro || "";
                this.state.pinGerente = "";
                return;
            }
            this.state.faltas = null;
            this.state.pinGerente = "";
            this.state.resultado = r;
        } catch (erro) {
            this.notification.add(erro?.data?.message || _t("Não deu para finalizar."), { type: "danger", sticky: true });
        } finally {
            this.state.enviando = false;
        }
    }
}

registry.category("actions").add("boteco_cozinha.producao", TelaProducao);
