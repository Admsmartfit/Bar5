/** @odoo-module **/
// Configuração › Sistema › WhatsApp (conectar) — Etapa 35: QR Code como no WhatsApp Web.
import { Component, onMounted, onWillStart, onWillUnmount, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";

const ATUALIZAR_MS = 5000; // o QR expira em ~40 s: a tela confere a cada 5 s e pede outro quando precisa
const NOVO_QR_MS = 35000;

export class WhatsappConectar extends Component {
    static template = "boteco_cotacoes.WhatsappConectar";
    static props = ["*"];

    setup() {
        this.orm = useService("orm");
        this.notification = useService("notification");
        this.state = useState({ dados: null, qr: null, ocupado: false, qrEm: 0 });
        onWillStart(() => this.atualizar());
        let timer = null;
        onMounted(() => (timer = setInterval(() => this.atualizar(), ATUALIZAR_MS)));
        onWillUnmount(() => clearInterval(timer));
    }

    get conectado() {
        return this.state.dados?.estado === "open";
    }

    async atualizar() {
        try {
            this.state.dados = await this.orm.call("boteco.whatsapp", "estado", []);
        } catch {
            return;
        }
        if (this.conectado) {
            this.state.qr = null;
        } else if (this.state.qr && Date.now() - this.state.qrEm > NOVO_QR_MS) {
            await this.conectar(true); // QR venceu: pede outro sozinho
        }
    }

    async conectar(silencioso = false) {
        if (this.state.ocupado) {
            return;
        }
        this.state.ocupado = true;
        try {
            const r = await this.orm.call("boteco.whatsapp", "conectar", []);
            this.state.qr = r.qr;
            this.state.qrEm = Date.now();
        } catch (erro) {
            if (!silencioso) {
                this.notification.add(erro.data?.message || String(erro), { type: "danger" });
            }
        } finally {
            this.state.ocupado = false;
        }
    }

    async desconectar() {
        await this.orm.call("boteco.whatsapp", "desconectar", []);
        this.state.qr = null;
        await this.atualizar();
    }

    numeroBonito(numero) {
        const d = String(numero || "").replace(/\D/g, "").replace(/^55/, "");
        return d.length >= 10 ? `(${d.slice(0, 2)}) ${d.slice(2, -4)}-${d.slice(-4)}` : numero || "";
    }

    desde(texto) {
        return texto ? new Date(texto.replace(" ", "T") + "Z").toLocaleString("pt-BR") : "";
    }
}

registry.category("actions").add("boteco_whatsapp_conectar", WhatsappConectar);
