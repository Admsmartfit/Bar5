/** @odoo-module */
// Barra fixa da mesa: Chamar garçom, Pedir a conta, Minha conta, Pedir de novo, ofertas,
// tela de descanso (tablet) e trava de quiosque com PIN do gerente.
import { Component, onMounted, onWillUnmount, useState } from "@odoo/owl";
import { _t } from "@web/core/l10n/translation";
import { rpc } from "@web/core/network/rpc";
import { useSelfOrder } from "@pos_self_order/app/self_order_service";
import { selfOrderIndex } from "@pos_self_order/app/self_order_index";

export class BotecoMesa extends Component {
    static template = "boteco_autoatendimento.BotecoMesa";
    static props = {};

    setup() {
        this.selfOrder = useSelfOrder();
        this.state = useState({ painel: null, descanso: false, pin: "", erroPin: "" });
        this.ultimoToque = Date.now();
        const tocar = () => {
            this.ultimoToque = Date.now();
            if (this.state.descanso) {
                this.state.descanso = false;
            }
        };
        let timer = null;
        onMounted(() => {
            ["pointerdown", "keydown", "scroll"].forEach((ev) => window.addEventListener(ev, tocar, { passive: true }));
            timer = setInterval(() => this.conferirDescanso(), 5000);
            if (this.mesa.tablet) {
                // Quiosque: o botão "voltar" do navegador não sai do cardápio
                history.pushState(null, "", window.location.href);
                this._voltar = () => history.pushState(null, "", window.location.href);
                window.addEventListener("popstate", this._voltar);
            }
        });
        onWillUnmount(() => {
            ["pointerdown", "keydown", "scroll"].forEach((ev) => window.removeEventListener(ev, tocar));
            clearInterval(timer);
            if (this._voltar) {
                window.removeEventListener("popstate", this._voltar);
            }
        });
    }

    get mesa() {
        return this.selfOrder.botecoMesa || {};
    }

    get ativo() {
        return Boolean(this.selfOrder.botecoIdentificador) && this.selfOrder.config.self_ordering_mode === "mobile";
    }

    get ofertas() {
        return this.selfOrder.botecoCardapio?.ofertas || [];
    }

    get aviso() {
        const m = this.mesa;
        if (m.semRede) {
            return { tipo: "erro", texto: _t("Sem conexão. O que você pedir fica guardado e sai quando a rede voltar.") };
        }
        if (m.estado === "fora_da_rede") {
            return { tipo: "erro", texto: _t("Conecte-se ao Wi-Fi do bar para fazer pedidos. Você pode ver o cardápio.") };
        }
        if (m.aguardandoLiberacao) {
            return { tipo: "info", texto: _t("Aguardando o garçom liberar este celular…") };
        }
        if (m.estado === "pendente" && !m.tablet) {
            return { tipo: "info", texto: _t("Monte seu pedido. No primeiro envio o garçom libera seu celular com um toque.") };
        }
        return null;
    }

    formatar(valor) {
        return this.selfOrder.formatMonetary ? this.selfOrder.formatMonetary(valor) : `R$ ${Number(valor || 0).toFixed(2).replace(".", ",")}`;
    }

    conferirDescanso() {
        const limite = (this.mesa.descanso_segundos || 120) * 1000;
        if (this.mesa.tablet && !this.state.descanso && !this.state.painel && Date.now() - this.ultimoToque > limite) {
            this.state.descanso = true;
        }
    }

    async chamar(tipo) {
        await this.selfOrder.botecoChamar(tipo);
    }

    async abrirConta() {
        await this.selfOrder.botecoAtualizarStatus();
        this.state.painel = "conta";
    }

    async abrirPedirDeNovo() {
        await this.selfOrder.botecoAtualizarStatus();
        this.state.painel = "denovo";
    }

    fechar() {
        this.state.painel = null;
    }

    produto(id) {
        return this.selfOrder.models["product.product"].get(id);
    }

    async adicionar(productId) {
        const produto = this.produto(productId);
        if (!produto || !produto.self_order_available) {
            return;
        }
        if (produto.attribute_line_ids?.length) {
            this.state.painel = null;
            this.selfOrder.router.navigate("product", { id: produto.id });
            return;
        }
        await this.selfOrder.addToCart(produto, 1, "", {}, {});
        this.selfOrder.notification.add(_t("%s no carrinho", produto.name), { type: "success" });
    }

    // ---------------------------------------------------------------- quiosque
    abrirSaida() {
        this.state.pin = "";
        this.state.erroPin = "";
        this.state.painel = "sair";
    }

    tecla(t) {
        this.state.erroPin = "";
        if (t === "apagar") {
            this.state.pin = this.state.pin.slice(0, -1);
        } else if (this.state.pin.length < 6) {
            this.state.pin += t;
        }
    }

    async confirmarSaida() {
        const resposta = await rpc("/boteco/mesa/sair_quiosque", {
            access_token: this.selfOrder.access_token,
            table_identifier: this.selfOrder.botecoIdentificador,
            pin: this.state.pin,
        });
        if (!resposta.ok) {
            this.state.erroPin = resposta.erro;
            this.state.pin = "";
            return;
        }
        try {
            localStorage.removeItem("boteco_tablet");
        } catch {
            // ignora
        }
        window.location.href = "/web/login";
    }
}

// Componente raiz do autoatendimento passa a conhecer a barra da mesa
selfOrderIndex.components = { ...selfOrderIndex.components, BotecoMesa };
