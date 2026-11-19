/** @odoo-module */
// PDV do garçom: liberar celular do QR (um toque), conferir idade (+18) da mesa e
// resolver pedidos do tablet retidos na quarentena N+X (Etapa 16).
//
// Auditoria (risco 3): nada disso trava mais a tela de quem está lançando pedido. Cada caso vira uma
// PENDÊNCIA (sino + aviso pequeno + contador no botão "Pendências" da barra). Resolveu em qualquer tablet,
// some de todos. Só se ninguém resolver em 60 s é que a janela abre sozinha (para não ficar esquecida).
import { reactive } from "@odoo/owl";
import { patch } from "@web/core/utils/patch";
import { _t } from "@web/core/l10n/translation";
import { ConfirmationDialog } from "@web/core/confirmation_dialog/confirmation_dialog";
import { PosStore } from "@point_of_sale/app/store/pos_store";
import { tocarSom } from "@boteco_pos/app/utils";
import { botecoPode } from "@boteco_pos/app/autorizacao_popup";
import { QuarentenaDialog } from "@boteco_autoatendimento/pos/quarentena_dialog";

export const ESCALAR_MS = 60000;

patch(PosStore.prototype, {
    async setup() {
        await super.setup(...arguments);
        this.botecoPendencias = reactive({ itens: [] });
        this.botecoJanelas = new Map(); // chave -> função que fecha a janela aberta
        this.botecoTimers = new Map();
        this.data.connectWebSocket("BOTECO_APROVAR", (dados) =>
            this.botecoAdicionarPendencia({ chave: `disp-${dados.id}`, tipo: "celular", mesa: dados.mesa, dados })
        );
        this.data.connectWebSocket("BOTECO_DISPOSITIVO", (dados) => this.botecoRemoverPendencia(`disp-${dados.id}`));
        this.data.connectWebSocket("BOTECO_MAIOR18", (dados) =>
            this.botecoAdicionarPendencia({ chave: `idade-${dados.mesa_id}`, tipo: "idade", mesa: dados.mesa, dados })
        );
        this.data.connectWebSocket("BOTECO_MESA", (dados) => {
            if (dados.evento === "maior18_ok") {
                this.botecoRemoverPendencia(`idade-${dados.id}`);
            }
        });
        this.data.connectWebSocket("BOTECO_PEDIDO_RETIDO", (dados) =>
            this.botecoAdicionarPendencia({ chave: `quar-${dados.pedido_id}`, tipo: "quarentena", mesa: dados.mesa, dados })
        );
        this.data.connectWebSocket("BOTECO_ANOMALIA_RESOLVIDA", (dados) => this.botecoFecharQuarentena(dados));
        // PDV aberto depois do alerta: mostra o que ainda está esperando (sem som)
        if (botecoPode(this, "pode_aprovar_qr")) {
            try {
                const pendentes = await this.data.call("pos.order", "boteco_pedidos_retidos", []);
                (pendentes || []).forEach((dados) =>
                    this.botecoAdicionarPendencia(
                        { chave: `quar-${dados.pedido_id}`, tipo: "quarentena", mesa: dados.mesa, dados },
                        false
                    )
                );
            } catch {
                // sem rede na abertura: os próximos alertas chegam pelo websocket
            }
        }
    },

    // ------------------------------------------------------------------ fila de pendências
    botecoAdicionarPendencia(item, comAviso = true) {
        if (!botecoPode(this, "pode_aprovar_qr")) {
            return;
        }
        const itens = this.botecoPendencias.itens;
        const existente = itens.find((i) => i.chave === item.chave);
        if (existente) {
            existente.dados = item.dados; // novo envio do mesmo pedido: atualiza
        } else {
            itens.push({ ...item, desde: Date.now() });
        }
        // Janela já aberta (ex.: quarentena atualizada): reabre com os dados novos
        if (this.botecoJanelas.has(item.chave)) {
            this.botecoJanelas.get(item.chave)();
            this.botecoResolver(item.chave);
        }
        if (comAviso && !existente) {
            tocarSom("bell");
            this.notification.add(_t("Mesa %(m)s: %(o)s. Toque em Pendências.", { m: item.mesa, o: this.botecoRotulo(item) }), {
                type: "warning",
            });
        }
        clearTimeout(this.botecoTimers.get(item.chave));
        this.botecoTimers.set(
            item.chave,
            setTimeout(() => {
                // Ninguém resolveu: abre a janela para não ficar esquecida
                if (this.botecoPendencias.itens.some((i) => i.chave === item.chave) && !this.botecoJanelas.has(item.chave)) {
                    tocarSom("bell");
                    this.botecoResolver(item.chave);
                }
            }, ESCALAR_MS)
        );
    },

    botecoRemoverPendencia(chave) {
        const itens = this.botecoPendencias.itens;
        const i = itens.findIndex((p) => p.chave === chave);
        if (i >= 0) {
            itens.splice(i, 1);
        }
        clearTimeout(this.botecoTimers.get(chave));
        this.botecoTimers.delete(chave);
        const fechar = this.botecoJanelas.get(chave);
        if (fechar) {
            this.botecoJanelas.delete(chave);
            fechar(); // resolvido em outro tablet: fecha aqui também
        }
    },

    botecoRotulo(item) {
        return {
            celular: _t("celular quer pedir"),
            idade: _t("conferir idade (+18)"),
            quarentena: _t("pedido fora do normal"),
        }[item.tipo];
    },

    /** Abre a janela de decisão de uma pendência (pelo botão Pendências ou depois de 60 s). */
    botecoResolver(chave) {
        const item = this.botecoPendencias.itens.find((i) => i.chave === chave);
        if (!item || this.botecoJanelas.has(chave)) {
            return;
        }
        const aoFechar = { onClose: () => this.botecoJanelas.delete(chave) };
        let fechar;
        if (item.tipo === "quarentena") {
            fechar = this.dialog.add(QuarentenaDialog, { dados: item.dados, pos: this }, aoFechar);
        } else if (item.tipo === "celular") {
            const dados = item.dados;
            fechar = this.dialog.add(
                ConfirmationDialog,
                {
                    title: _t("Mesa %s: celular quer pedir", dados.mesa),
                    body: _t("Confira se a pessoa está mesmo na mesa %s e libere com um toque.", dados.mesa),
                    confirmLabel: _t("Liberar"),
                    cancelLabel: _t("Recusar"),
                    confirm: async () => {
                        await this.data.call("boteco.dispositivo", "boteco_aprovar", [[dados.id]]);
                        this.botecoRemoverPendencia(chave);
                    },
                    cancel: async () => {
                        await this.data.call("boteco.dispositivo", "boteco_recusar", [[dados.id]]);
                        this.botecoRemoverPendencia(chave);
                    },
                },
                aoFechar
            );
        } else {
            const dados = item.dados;
            fechar = this.dialog.add(
                ConfirmationDialog,
                {
                    title: _t("Mesa %s: bebida alcoólica (+18)", dados.mesa),
                    body: _t(
                        "Primeira bebida alcoólica da mesa. Confira a idade de quem vai beber. " +
                            "O pedido só vai para o bar depois da sua confirmação."
                    ),
                    confirmLabel: _t("Todos têm 18+"),
                    cancelLabel: _t("Depois"),
                    confirm: async () => {
                        await this.data.call("restaurant.table", "boteco_confirmar_maior18", [[dados.mesa_id]]);
                        this.botecoRemoverPendencia(chave);
                    },
                    cancel: () => {},
                },
                aoFechar
            );
        }
        this.botecoJanelas.set(chave, fechar);
    },

    botecoFecharQuarentena(dados) {
        const chave = `quar-${dados.pedido_id}`;
        const estava = this.botecoPendencias.itens.some((i) => i.chave === chave);
        this.botecoRemoverPendencia(chave);
        if (estava) {
            this.notification.add(_t("Mesa %s: pedido resolvido por %s", dados.mesa, dados.resolvido_por || "?"), {
                type: "info",
            });
        }
    },
});
