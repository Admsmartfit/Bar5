/** @odoo-module */
/*
 * Tela de produção (KDS) do Boteco. Ideia de fluxo inspirada no Mosaic do URY; código próprio.
 *
 * - Cartões por pedido, em ordem de chegada; toque = próximo estado (fila → preparando → pronto).
 * - Depois do toque aparece "Desfazer" por 5 segundos (sem "Tem certeza?").
 * - Toque longo (0,6 s) abre: reimprimir / voltar estado.
 * - Cronômetro em cada cartão; cor pelo tempo: verde até 10 min, amarelo até 20, vermelho acima.
 * - Som ao chegar pedido. Atualiza em tempo real pelo barramento do Odoo e confere a cada 20 s.
 * - Funciona só com toque: botões de 64 px, sem teclado e sem mouse.
 */
import { Component, onMounted, onWillStart, onWillUnmount, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { _t } from "@web/core/l10n/translation";

const CONFERENCIA_MS = 20000;
const DESFAZER_MS = 5000;
const TOQUE_LONGO_MS = 600;

export const ROTULOS_ESTADO = {
    aguardando: _t("Na fila"),
    preparando: _t("Preparando"),
    pronto: _t("Pronto"),
    entregue: _t("Entregue"),
};
const ROTULOS_ORIGEM = { garcom: _t("Garçom"), caixa: _t("Caixa"), tablet: _t("Tablet"), qr: _t("QR"), qr_bebidas: _t("QR BEBIDAS") };

export class KdsTela extends Component {
    static template = "boteco_kds.KdsTela";
    static props = ["*"];

    setup() {
        this.orm = useService("orm");
        this.bus = useService("bus_service");
        this.notification = useService("notification");
        const params = this.props.action?.params || {};
        this.setor = params.setor || "todos";
        this.modo = params.modo || "producao";
        this.titulo = this.props.action?.name || _t("Produção");
        this.state = useState({
            tickets: [],
            cancelamentos: [],
            impressorasParadas: [],
            esperandoImpressao: 0,
            agora: Date.now(),
            desfazer: null,
            menu: null,
            conectado: true,
            telaCheia: false,
            carregando: true,
            avancado: false, // Etapa 21: totalizador de grelha, pacing e bump bar
        });
        this._aoTecla = (ev) => this.aoTecla(ev);
        this.criadoLocal = new Map(); // id -> instante local em que o ticket foi criado
        this.som = new Audio("/point_of_sale/static/src/sounds/bell.mp3");
        this.canal = null;
        this.timers = [];
        this._aoNotificar = (payload) => this.aoAtualizar(payload);
        this._aoImpressora = (payload) => this.aoImpressora(payload);
        this._aoAlerta = (payload) => this.notification.add(payload.mensagem, { type: "danger", sticky: true });

        onWillStart(() => this.carregar());
        onMounted(() => {
            this.bus.subscribe("boteco_kds/atualizar", this._aoNotificar);
            this.bus.subscribe("boteco_kds/impressora", this._aoImpressora);
            this.bus.subscribe("boteco_kds/alerta", this._aoAlerta);
            this.timers.push(setInterval(() => (this.state.agora = Date.now()), 1000));
            this.timers.push(setInterval(() => this.carregar(), CONFERENCIA_MS));
            window.addEventListener("keydown", this._aoTecla);
        });
        onWillUnmount(() => {
            this.bus.unsubscribe("boteco_kds/atualizar", this._aoNotificar);
            this.bus.unsubscribe("boteco_kds/impressora", this._aoImpressora);
            this.bus.unsubscribe("boteco_kds/alerta", this._aoAlerta);
            if (this.canal) {
                this.bus.deleteChannel(this.canal);
            }
            this.timers.forEach(clearInterval);
            window.removeEventListener("keydown", this._aoTecla);
            document.body.classList.remove("o_boteco_kds_cheia");
        });
    }

    // ------------------------------------------------------------------ dados
    async carregar() {
        try {
            const dados = await this.orm.call("boteco.kds.pedido", "kds_dados", [this.setor]);
            if (dados.canal && dados.canal !== this.canal) {
                this.canal = dados.canal;
                this.bus.addChannel(this.canal);
            }
            this.aplicarLista(dados.tickets, true);
            this.state.cancelamentos = dados.cancelamentos;
            this.state.impressorasParadas = dados.impressoras_paradas;
            this.state.esperandoImpressao = dados.tickets_esperando_impressao;
            this.state.avancado = Boolean(dados.avancado);
            this.state.conectado = true;
        } catch {
            this.state.conectado = false;
        } finally {
            this.state.carregando = false;
        }
    }

    registrarRelogio(ticket) {
        if (!this.criadoLocal.has(ticket.id)) {
            this.criadoLocal.set(ticket.id, Date.now() - (ticket.segundos || 0) * 1000);
        }
        if (ticket.iniciar_em_segundos) {
            this.iniciarLocal = this.iniciarLocal || new Map();
            this.iniciarLocal.set(ticket.id, Date.now() + ticket.iniciar_em_segundos * 1000);
        }
    }

    // ------------------------------------------------------------------ Etapa 21 (KDS avançado)
    /** Totalizador de grelha: soma dos itens iguais ainda na fila ou em preparo. */
    get totalizador() {
        if (!this.state.avancado) {
            return [];
        }
        const soma = new Map();
        for (const t of this.ticketsVisiveis) {
            if (!["aguardando", "preparando"].includes(t.estado)) {
                continue;
            }
            for (const i of t.itens) {
                const chave = `${i.nome}|${i.atributos || ""}`;
                const atual = soma.get(chave) || { nome: i.nome, atributos: i.atributos, quantidade: 0 };
                atual.quantidade += i.quantidade;
                soma.set(chave, atual);
            }
        }
        return [...soma.values()].sort((a, b) => b.quantidade - a.quantidade);
    }

    /** Pacing: quanto falta para começar este cartão (0 = já pode). */
    esperaPacing(ticket) {
        if (!this.state.avancado || ticket.estado !== "aguardando") {
            return 0;
        }
        const quando = this.iniciarLocal?.get(ticket.id);
        return quando ? Math.max(0, Math.ceil((quando - this.state.agora) / 1000)) : 0;
    }

    formatarEspera(segundos) {
        return `${Math.floor(segundos / 60)}:${String(segundos % 60).padStart(2, "0")}`;
    }

    /** Bump bar (teclado numérico USB): 1-9 avança o cartão daquela posição; 0 desfaz. */
    aoTecla(ev) {
        if (!this.state.avancado || ev.ctrlKey || ev.altKey || ev.metaKey) {
            return;
        }
        if (["INPUT", "TEXTAREA"].includes(document.activeElement?.tagName)) {
            return;
        }
        const tecla = ev.key;
        if (tecla === "0" || tecla === "Backspace") {
            ev.preventDefault();
            this.desfazer();
            return;
        }
        const n = parseInt(tecla, 10);
        if (n >= 1 && n <= 9) {
            const ticket = this.ticketsVisiveis[n - 1];
            if (ticket) {
                ev.preventDefault();
                this._longo = false;
                this.tocarCartao(ticket);
            }
        }
    }

    aplicarLista(tickets, substituir = false) {
        const atual = new Map(substituir ? [] : this.state.tickets.map((t) => [t.id, t]));
        for (const t of tickets) {
            this.registrarRelogio(t);
            atual.set(t.id, t);
        }
        this.state.tickets = [...atual.values()];
    }

    pertenceAoSetor(ticket) {
        return this.setor === "todos" || ticket.setor === this.setor;
    }

    aoAtualizar({ evento, tickets }) {
        const meus = tickets.filter((t) => this.pertenceAoSetor(t));
        if (!meus.length) {
            return;
        }
        const novos = meus.filter((t) => t.tipo === "novo");
        const cancelamentos = meus.filter((t) => t.tipo === "cancelamento");
        if (novos.length) {
            this.aplicarLista(novos);
        }
        if (cancelamentos.length) {
            this.state.cancelamentos = [...this.state.cancelamentos, ...cancelamentos];
        }
        if (evento === "novo" && this.modo === "producao") {
            this.tocar();
        }
        if (evento === "pronto" && this.modo === "expedicao") {
            this.tocar();
        }
    }

    aoImpressora(payload) {
        const outras = this.state.impressorasParadas.filter((i) => i.id !== payload.id);
        this.state.impressorasParadas = payload.ok ? outras : [...outras, payload];
        this.notification.add(payload.mensagem, { type: payload.ok ? "success" : "danger", sticky: !payload.ok });
    }

    tocar() {
        try {
            this.som.currentTime = 0;
            this.som.play().catch(() => {});
        } catch {
            // sem áudio
        }
    }

    // ------------------------------------------------------------------ exibição
    get ticketsVisiveis() {
        const estados = this.modo === "expedicao" ? ["pronto"] : ["aguardando", "preparando", "pronto"];
        return this.state.tickets
            .filter((t) => t.tipo === "novo" && estados.includes(t.estado) && this.pertenceAoSetor(t))
            .sort(
                (a, b) =>
                    (b.prioridade ? 1 : 0) - (a.prioridade ? 1 : 0) ||
                    (this.criadoLocal.get(a.id) || 0) - (this.criadoLocal.get(b.id) || 0)
            );
    }

    get contadores() {
        const visiveis = this.state.tickets.filter((t) => this.pertenceAoSetor(t) && t.tipo === "novo");
        return {
            fila: visiveis.filter((t) => t.estado === "aguardando").length,
            preparando: visiveis.filter((t) => t.estado === "preparando").length,
            prontos: visiveis.filter((t) => t.estado === "pronto").length,
        };
    }

    segundos(ticket) {
        const inicio = this.criadoLocal.get(ticket.id) || this.state.agora;
        return Math.max(0, Math.floor((this.state.agora - inicio) / 1000));
    }

    cronometro(ticket) {
        const s = this.segundos(ticket);
        const min = Math.floor(s / 60);
        const seg = String(s % 60).padStart(2, "0");
        return `${min}:${seg}`;
    }

    corTempo(ticket) {
        if (ticket.estado === "pronto") {
            return "pronto";
        }
        const min = this.segundos(ticket) / 60;
        return min <= 10 ? "verde" : min <= 20 ? "amarelo" : "vermelho";
    }

    rotuloEstado(estado) {
        return ROTULOS_ESTADO[estado] || estado;
    }

    rotuloOrigem(origem) {
        return ROTULOS_ORIGEM[origem] || "";
    }

    rotuloAcao(ticket) {
        if (this.modo === "expedicao") {
            return _t("Entregue");
        }
        return ticket.estado === "aguardando" ? _t("Começar") : ticket.estado === "preparando" ? _t("Pronto!") : _t("Entregue");
    }

    formatarQtd(qtd) {
        return Number.isInteger(qtd) ? String(qtd) : String(qtd).replace(".", ",");
    }

    // ------------------------------------------------------------------ toques
    inicioToque(ticket) {
        clearTimeout(this._timerLongo);
        this._longo = false;
        this._timerLongo = setTimeout(() => {
            this._longo = true;
            this.state.menu = ticket.id;
        }, TOQUE_LONGO_MS);
    }

    fimToque() {
        clearTimeout(this._timerLongo);
    }

    async tocarCartao(ticket) {
        if (this._longo) {
            this._longo = false;
            return;
        }
        if (this.modo === "expedicao" || ticket.estado === "pronto") {
            await this.entregar(ticket);
            return;
        }
        const anterior = ticket.estado;
        try {
            const dados = await this.orm.call("boteco.kds.pedido", "kds_avancar", [[ticket.id]]);
            this.aplicarLista(dados);
            this.mostrarDesfazer(ticket, anterior);
        } catch {
            this.state.conectado = false;
        }
    }

    async entregar(ticket) {
        await this.orm.call("boteco.kds.pedido", "kds_entregar", [[ticket.id]]);
        ticket.estado = "entregue";
        this.state.tickets = this.state.tickets.filter((t) => t.id !== ticket.id);
        this.mostrarDesfazer(ticket, "pronto");
    }

    mostrarDesfazer(ticket, anterior) {
        clearTimeout(this._timerDesfazer);
        this.state.desfazer = { id: ticket.id, mesa: ticket.mesa, anterior };
        this._timerDesfazer = setTimeout(() => (this.state.desfazer = null), DESFAZER_MS);
    }

    async desfazer() {
        const d = this.state.desfazer;
        if (!d) {
            return;
        }
        this.state.desfazer = null;
        const dados = await this.orm.call("boteco.kds.pedido", "kds_voltar", [[d.id]]);
        this.aplicarLista(dados);
    }

    async reimprimir(ticketId) {
        this.state.menu = null;
        try {
            await this.orm.call("boteco.kds.pedido", "kds_reimprimir", [[ticketId]]);
            this.notification.add(_t("Ticket enviado para a impressora."), { type: "success" });
        } catch (erro) {
            this.notification.add(erro?.data?.message || _t("Não deu para reimprimir."), { type: "danger" });
        }
    }

    async priorizar(ticket) {
        this.state.menu = null;
        const motivo = ticket.prioridade ? "" : window.prompt(_t("Por que este pedido passa na frente? (ex.: cliente esperando há muito)")) || "";
        try {
            const dados = await this.orm.call("boteco.kds.pedido", "kds_priorizar", [[ticket.id], motivo]);
            this.aplicarLista(dados);
        } catch (erro) {
            this.notification.add(erro?.data?.message || _t("Não deu."), { type: "danger" });
        }
    }

    async voltarEstado(ticketId) {
        this.state.menu = null;
        const dados = await this.orm.call("boteco.kds.pedido", "kds_voltar", [[ticketId]]);
        this.aplicarLista(dados);
    }

    fecharCancelamento(id) {
        this.state.cancelamentos = this.state.cancelamentos.filter((c) => c.id !== id);
    }

    alternarTelaCheia() {
        this.state.telaCheia = !this.state.telaCheia;
        document.body.classList.toggle("o_boteco_kds_cheia", this.state.telaCheia);
        if (this.state.telaCheia && document.documentElement.requestFullscreen) {
            document.documentElement.requestFullscreen().catch(() => {});
        } else if (!this.state.telaCheia && document.fullscreenElement) {
            document.exitFullscreen().catch(() => {});
        }
    }
}

registry.category("actions").add("boteco_kds.tela", KdsTela);
