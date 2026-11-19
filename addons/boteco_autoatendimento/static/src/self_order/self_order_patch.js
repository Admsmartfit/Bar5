/** @odoo-module */
/*
 * Regras do boteco no autoatendimento (tablet da mesa e QR no celular):
 *  - identifica o aparelho (cookie do servidor) e a mesa;
 *  - primeiro pedido do celular: chama o garçom para liberar e envia sozinho quando ele liberar;
 *  - primeiro item com álcool da mesa: aviso de +18 (o garçom confere antes de preparar);
 *  - sem rede: o carrinho fica guardado no aparelho e o envio acontece quando a rede voltar;
 *  - tablet: volta para a tela inicial e limpa o histórico quando a conta fecha.
 */
import { patch } from "@web/core/utils/patch";
import { _t } from "@web/core/l10n/translation";
import { rpc } from "@web/core/network/rpc";
import { SelfOrder } from "@pos_self_order/app/self_order_service";

const STATUS_MS = 10000;

patch(SelfOrder.prototype, {
    async setup() {
        await super.setup(...arguments);
        const url = new URL(window.location.href);
        const chaveMesa = `boteco_mesa_${this.config.id}`;
        const tabletUrl = url.searchParams.get("boteco_tablet");
        if (tabletUrl) {
            try {
                localStorage.setItem("boteco_tablet", tabletUrl);
            } catch {
                // navegador sem armazenamento: segue só com a URL
            }
        }
        let tablet = tabletUrl;
        let mesaGuardada = null;
        try {
            tablet = tablet || localStorage.getItem("boteco_tablet");
            mesaGuardada = localStorage.getItem(chaveMesa);
        } catch {
            // ignora
        }
        const identificador = this.router.getTableIdentifier() || mesaGuardada;
        if (identificador) {
            try {
                localStorage.setItem(chaveMesa, identificador);
            } catch {
                // ignora
            }
        }
        // QR expresso de bebidas (Etapa 36): o 2º QR da mesa traz ?modo=bebidas. O servidor lê o modo
        // por um cookie (o pedido em si não carrega campos extras). Ler o QR do cardápio desliga o modo.
        const modoBebidas = !tablet && url.searchParams.get("modo") === "bebidas";
        document.cookie = modoBebidas
            ? "boteco_modo=bebidas; path=/; max-age=43200; SameSite=Lax"
            : "boteco_modo=; path=/; max-age=0; SameSite=Lax";
        this.botecoTabletToken = tablet || null;
        this.botecoIdentificador = identificador;
        this.botecoMesa = {
            estado: identificador ? "carregando" : "sem_mesa",
            tablet: Boolean(tablet),
            conta: null,
            pedir_de_novo: [],
            aguardandoLiberacao: false,
            semRede: false,
            modo: modoBebidas ? "bebidas" : null,
            bebidas_mesa: [],
        };
        if (!identificador || this.config.self_ordering_mode !== "mobile") {
            return;
        }
        await this.botecoEntrar();
        if (this.botecoModoBebidas()) {
            this.botecoAtualizarStatus();
        }
        setInterval(() => this.botecoAtualizarStatus(), STATUS_MS);
        this.data.connectWebSocket("BOTECO_MESA", (dados) => this.botecoAoMudarMesa(dados));
        this.data.connectWebSocket("BOTECO_DISPOSITIVO", (dados) => {
            if (dados.id === this.botecoMesa.id) {
                this.botecoAtualizarStatus();
            }
        });
        window.addEventListener("online", () => this.botecoAoVoltarRede());
        window.addEventListener("offline", () => (this.botecoMesa.semRede = true));
    },

    // ------------------------------------------------------------------ servidor
    async botecoEntrar() {
        try {
            const resposta = await fetch("/boteco/mesa/entrar", {
                method: "POST",
                credentials: "same-origin",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    access_token: this.access_token,
                    table_identifier: this.botecoIdentificador,
                    tablet_token: this.botecoTabletToken,
                }),
            });
            Object.assign(this.botecoMesa, await resposta.json());
        } catch {
            this.botecoMesa.semRede = true;
        }
    },

    async botecoAtualizarStatus() {
        if (!this.botecoIdentificador) {
            return;
        }
        try {
            const dados = await rpc(
                "/boteco/mesa/status",
                { access_token: this.access_token, table_identifier: this.botecoIdentificador },
                { silent: true }
            );
            const estavaEsperando = this.botecoMesa.aguardandoLiberacao;
            const estavaEmConferencia = this.botecoMesa.conta?.em_conferencia;
            Object.assign(this.botecoMesa, dados, { semRede: false });
            const emConferencia = Boolean(dados.conta?.em_conferencia);
            if (emConferencia && !estavaEmConferencia) {
                this.notification.add(
                    _t("Recebemos seu pedido! O garçom vai confirmar com a mesa antes de preparar."),
                    { type: "info" }
                );
            }
            if (estavaEsperando && dados.estado === "aprovado") {
                this.botecoMesa.aguardandoLiberacao = false;
                this._botecoFecharAviso?.();
                this.notification.add(_t("Celular liberado! Enviando seu pedido…"), { type: "success" });
                await this.confirmOrder();
            }
        } catch {
            this.botecoMesa.semRede = !navigator.onLine;
        }
    },

    /** Modo "Bebidas rápido": só vale com o recurso ligado na Central de Recursos. */
    botecoModoBebidas() {
        return this.botecoMesa?.modo === "bebidas" && Boolean(this.botecoMesa?.qr_bebidas_ativo);
    },

    botecoSoBebidasNoCarrinho() {
        // Celular não liberado só pediu pelo QR de bebidas: todas as linhas da conta dele são bebidas
        const linhas = this.currentOrder?.lines || [];
        return linhas.length > 0 && linhas.every((l) => l.product_id?.boteco_e_bebida);
    },

    botecoRecurso(codigo) {
        return Boolean(this.botecoMesa?.recursos?.[codigo]);
    },

    async botecoChamar(tipo, motivo = null) {
        const resposta = await rpc("/boteco/mesa/chamar", {
            access_token: this.access_token,
            table_identifier: this.botecoIdentificador,
            tipo,
            motivo,
        });
        if (resposta.ok) {
            this.notification.add(
                tipo === "conta" ? _t("Pronto! O garçom já vai trazer a conta.") : _t("Pronto! O garçom já vem."),
                { type: "success" }
            );
            if (tipo === "conta") {
                this.botecoMesa.pediu_conta = true;
            } else {
                this.botecoMesa.chamou_garcom = true;
            }
        } else {
            this.notification.add(resposta.erro, { type: "warning" });
        }
    },

    botecoAoMudarMesa(dados) {
        if (dados.id !== this.botecoMesa.mesa_id) {
            return;
        }
        this.botecoMesa.chamou_garcom = dados.boteco_chamou_garcom;
        this.botecoMesa.pediu_conta = dados.boteco_pediu_conta;
        if (dados.evento === "maior18_ok") {
            this.botecoMesa.maior18_confirmado = true;
        }
        if (dados.evento === "pedido_aprovado") {
            this.notification.add(_t("Pedido confirmado pelo garçom e enviado para o preparo."), { type: "success" });
        } else if (dados.evento === "pedido_recusado") {
            this.notification.add(
                _t("O garçom não confirmou o último pedido. Ele vai passar na mesa para conversar com você."),
                { type: "warning", sticky: true }
            );
        }
        if (dados.evento === "liberada") {
            this.botecoAoFecharConta();
        } else {
            this.botecoAtualizarStatus();
        }
    },

    async botecoAoFecharConta() {
        if (this.botecoMesa.tablet) {
            // Tablet da mesa: limpa o histórico e volta para as boas-vindas
            try {
                await this.data.resetIndexedDB();
            } catch {
                // segue mesmo assim
            }
            window.location.reload();
        } else {
            this.botecoMesa.estado = "pendente";
            this.botecoMesa.conta = null;
        }
    },

    async botecoAoVoltarRede() {
        this.botecoMesa.semRede = false;
        if (this.botecoMesa.envioPendente) {
            this.botecoMesa.envioPendente = false;
            this.notification.add(_t("Conexão de volta: enviando o pedido guardado."), { type: "info" });
            await this.confirmOrder();
        }
    },

    botecoTemAlcoolNoCarrinho() {
        return (this.currentOrder?.lines || []).some((l) => l.product_id?.boteco_maior_18);
    },

    // ------------------------------------------------------------------ envio
    async sendDraftOrderToServer() {
        const mesa = this.botecoMesa;
        if (!mesa || !this.botecoIdentificador || this.config.self_ordering_mode !== "mobile") {
            return super.sendDraftOrderToServer(...arguments);
        }
        // Tablet neutro (Etapa 16): trava de envio duplo enquanto o primeiro toque não terminou.
        // O próprio pedido tem uuid único: o servidor também nunca duplica.
        const travar = this.botecoRecurso("tablet_neutro_anti_burst");
        if (travar && this._botecoEnviando) {
            return false;
        }
        this._botecoEnviando = travar;
        try {
            if (!(await this._botecoPodeEnviar(mesa))) {
                return false;
            }
            const resultado = await super.sendDraftOrderToServer(...arguments);
            if (resultado === false && !navigator.onLine) {
                mesa.envioPendente = true;
            }
            if (resultado) {
                this.botecoAtualizarStatus();
            }
            return resultado;
        } finally {
            this._botecoEnviando = false;
        }
    },

    /** Conferências antes do envio: rede, liberação do celular e aviso de +18. */
    async _botecoPodeEnviar(mesa) {
        if (!navigator.onLine) {
            mesa.envioPendente = true;
            mesa.semRede = true;
            this.notification.add(
                _t("Sem internet agora. Seu pedido está guardado neste aparelho e será enviado quando a conexão voltar."),
                { type: "warning", sticky: true }
            );
            return false;
        }
        if (mesa.estado === "fora_da_rede") {
            this.notification.add(_t("Para pedir, conecte-se ao Wi-Fi do bar. O cardápio continua aberto para consulta."), {
                type: "warning",
                sticky: true,
            });
            return false;
        }
        if (mesa.estado !== "aprovado" && this.botecoModoBebidas()) {
            // QR de bebidas: sem liberação do garçom, só bebidas e com a mesa aberta
            if (!mesa.mesa_aberta) {
                this.notification.add(_t("A mesa ainda não foi aberta. Peça ao garçom para abrir a mesa."), {
                    type: "warning",
                    sticky: true,
                });
                return false;
            }
            if (!this.botecoSoBebidasNoCarrinho()) {
                this.notification.add(
                    _t("Pelo QR de bebidas dá para pedir só bebidas. Para comida, use o QR do cardápio."),
                    { type: "warning", sticky: true }
                );
                return false;
            }
        } else if (mesa.estado !== "aprovado") {
            const resposta = await rpc("/boteco/mesa/solicitar", {
                access_token: this.access_token,
                table_identifier: this.botecoIdentificador,
            });
            Object.assign(mesa, resposta);
            if (resposta.estado !== "aprovado") {
                mesa.aguardandoLiberacao = true;
                this._botecoFecharAviso = this.notification.add(
                    _t("Chamamos o garçom para liberar seu celular. Seu pedido está guardado e sai sozinho assim que ele liberar."),
                    { type: "info", sticky: true }
                );
                return false;
            }
        }
        if (this.botecoTemAlcoolNoCarrinho() && !mesa.maior18_confirmado && !mesa.aviso18Mostrado) {
            mesa.aviso18Mostrado = true;
            this.notification.add(
                _t("Venda proibida para menores de 18 anos. O garçom vai conferir antes de preparar as bebidas."),
                { type: "warning", sticky: true }
            );
        }
        return true;
    },
});
