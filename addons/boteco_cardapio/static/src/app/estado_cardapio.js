/** @odoo-module */
/*
 * Estado dinâmico do cardápio (happy hour, ofertas relâmpago, "Acabou"), compartilhado
 * pelo PDV (garçom/caixa) e pelo autoatendimento (tablet da mesa e QR).
 *
 * - O servidor diz se o happy hour está ligado e a hora EXATA da próxima troca.
 * - A tela agenda um timer para essa hora (corrigindo a diferença de relógio do aparelho),
 *   então às 21:00:00 o preço volta ao normal sem recarregar.
 * - Mudanças (oferta lançada/esgotada, produto acabou) chegam pelo canal em tempo real
 *   BOTECO_CARDAPIO; a cada minuto há uma conferência de segurança.
 */
import { rpc } from "@web/core/network/rpc";
import { patch } from "@web/core/utils/patch";
import { ProductProduct } from "@point_of_sale/app/models/product_product";

// Estado lido pelo cálculo de preço (fora do sistema reativo, para não pesar no render).
export const estadoCardapio = {
    happyAtivo: false,
    ofertasPorProduto: new Map(),
    esgotados: new Set(),
    diferencaRelogio: 0,
};

const INTERVALO_CONFERENCIA_MS = 60 * 1000;
const MAX_TIMER_MS = 2 ** 31 - 1;

export class SincronizadorCardapio {
    /**
     * @param {Object} store objeto reativo (PosStore ou SelfOrder); recebe `botecoCardapio`
     * @param {Object} opcoes {configId, accessToken, conectar(canal, callback)}
     */
    constructor(store, { configId, accessToken, conectar }) {
        this.store = store;
        this.configId = configId;
        this.accessToken = accessToken;
        this.conectar = conectar;
        this.timerTroca = null;
        this.timerConferencia = null;
        this.store.botecoCardapio = { versao: 0, happyAtivo: false, ofertas: [] };
    }

    iniciar() {
        this.atualizar();
        this.timerConferencia = setInterval(() => this.atualizar(), INTERVALO_CONFERENCIA_MS);
        if (this.conectar) {
            this.conectar("BOTECO_CARDAPIO", () => this.atualizar());
        }
        window.addEventListener("online", () => this.atualizar());
        document.addEventListener("visibilitychange", () => {
            if (!document.hidden) {
                this.atualizar();
            }
        });
    }

    async atualizar() {
        try {
            const estado = await rpc(
                "/boteco/cardapio/estado",
                { config_id: this.configId, access_token: this.accessToken },
                { silent: true }
            );
            this.aplicar(estado);
        } catch {
            // Sem rede: mantém o último estado e o timer local continua valendo.
        }
    }

    aplicar(estado) {
        if (!estado) {
            return;
        }
        estadoCardapio.diferencaRelogio = (estado.agora || Date.now()) - Date.now();
        estadoCardapio.happyAtivo = Boolean(estado.happy_ativo);
        estadoCardapio.ofertasPorProduto = new Map(
            (estado.ofertas || []).map((oferta) => [oferta.product_id, oferta])
        );
        estadoCardapio.esgotados = new Set(estado.esgotados || []);
        this.agendarTroca(estado.proxima_troca);
        this.publicar(estado.ofertas || []);
    }

    agendarTroca(proximaTrocaServidor) {
        clearTimeout(this.timerTroca);
        if (!proximaTrocaServidor) {
            return;
        }
        // Hora da troca no relógio deste aparelho
        const local = proximaTrocaServidor - estadoCardapio.diferencaRelogio;
        const espera = Math.max(0, Math.min(local - Date.now(), MAX_TIMER_MS));
        this.timerTroca = setTimeout(() => {
            estadoCardapio.happyAtivo = !estadoCardapio.happyAtivo;
            this.publicar(this.store.botecoCardapio.ofertas);
            // Confirma com o servidor logo depois da virada
            setTimeout(() => this.atualizar(), 2000);
        }, espera);
    }

    publicar(ofertas) {
        // Mexer no objeto reativo faz as telas redesenharem os preços
        const reativo = this.store.botecoCardapio;
        reativo.happyAtivo = estadoCardapio.happyAtivo;
        reativo.ofertas = ofertas;
        reativo.versao = (reativo.versao || 0) + 1;
    }
}

patch(ProductProduct.prototype, {
    get_price(pricelist, quantity, price_extra = 0, recurring = false, ...resto) {
        const preco = super.get_price(pricelist, quantity, price_extra, recurring, ...resto);
        if (recurring) {
            return preco;
        }
        const extra = price_extra || 0;
        const oferta = estadoCardapio.ofertasPorProduto.get(this.id);
        if (oferta && oferta.restante >= (quantity || 1)) {
            return oferta.preco + extra;
        }
        if (estadoCardapio.happyAtivo && this.boteco_preco_happy > 0) {
            return this.boteco_preco_happy + extra;
        }
        return preco;
    },
    get canBeDisplayed() {
        return super.canBeDisplayed && !this.boteco_esgotado && !estadoCardapio.esgotados.has(this.id);
    },
    get botecoEmHappyHour() {
        return estadoCardapio.happyAtivo && this.boteco_preco_happy > 0;
    },
    get botecoOferta() {
        return estadoCardapio.ofertasPorProduto.get(this.id) || null;
    },
});
