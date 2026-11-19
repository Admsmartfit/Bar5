/** @odoo-module **/
// Ajuda rápida (Etapa 26): botão ?, F1 e Ctrl+K abrem um painel de busca ao lado da tela atual.
// A busca roda aqui no navegador (índice carregado uma vez): responde na hora, mesmo com Wi-Fi ruim.

import { Component, markup, reactive, useEffect, useRef, useState, onWillUnmount } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { session } from "@web/session";
import { useService } from "@web/core/utils/hooks";
import { rpc } from "@web/core/network/rpc";

const PALAVRAS_VAZIAS = new Set([
    "como", "faco", "fazer", "de", "do", "da", "dos", "das", "o", "a", "os", "as", "um", "uma", "e", "para",
    "pra", "no", "na", "nos", "nas", "eu", "meu", "minha", "que", "onde", "fica", "com", "em", "por", "qual",
]);

export function normalizar(texto) {
    return (texto || "")
        .normalize("NFD")
        .replace(/[̀-ͯ]/g, "")
        .toLowerCase();
}

export function palavras(texto) {
    return normalizar(texto)
        .split(/[^a-z0-9]+/)
        .filter((p) => p && !PALAVRAS_VAZIAS.has(p));
}

/** Distância de edição limitada (erro de digitação leve: "whatapp" ~ "whatsapp"). */
export function parecido(a, b) {
    if (Math.abs(a.length - b.length) > 1) {
        return false;
    }
    let i = 0;
    let j = 0;
    let erros = 0;
    while (i < a.length && j < b.length) {
        if (a[i] === b[j]) {
            i++;
            j++;
            continue;
        }
        if (++erros > 1) {
            return false;
        }
        if (a.length > b.length) {
            i++;
        } else if (a.length < b.length) {
            j++;
        } else {
            i++;
            j++;
        }
    }
    return erros + (a.length - i) + (b.length - j) <= 1;
}

function bate(token, listaPalavras) {
    return listaPalavras.some(
        (p) => p === token || (token.length >= 3 && p.startsWith(token)) || (token.length >= 5 && parecido(token, p))
    );
}

/** Pontua um item: cada campo tem peso; exige que a maioria das palavras buscadas apareça. */
export function pontuar(tokens, campos) {
    if (!tokens.length) {
        return 0;
    }
    let pontos = 0;
    let achadas = 0;
    for (const token of tokens) {
        let melhor = 0;
        for (const [texto, peso] of campos) {
            if (bate(token, palavras(texto))) {
                melhor = Math.max(melhor, peso);
            }
        }
        if (melhor) {
            achadas++;
            pontos += melhor;
        }
    }
    const cobertura = achadas / tokens.length;
    return cobertura >= 0.5 ? cobertura * 100 + pontos : 0;
}

/** Se algum resultado bate com todas as palavras, os que batem só com parte delas saem da lista. */
function soOsMelhores(lista) {
    const completos = lista.filter((r) => r.pontos >= 100);
    return completos.length ? completos : lista;
}

export function buscar(indice, consulta) {
    const tokens = palavras(consulta);
    const textoPassos = (html) => (html || "").replace(/<[^>]+>/g, " ");
    const artigos = indice.artigos
        .map((a) => ({
            item: a,
            pontos: pontuar(tokens, [
                [a.titulo, 4],
                [a.sinonimos, 4],
                [a.resumo, 2],
                [a.caminho || "", 1],
                [textoPassos(a.passos), 1],
            ]),
        }))
        .filter((r) => r.pontos > 0)
        .sort((x, y) => y.pontos - x.pontos);
    const telas = indice.telas
        .map((t) => ({ item: t, pontos: pontuar(tokens, [[t.nome, 3], [t.caminho, 1]]) }))
        .filter((r) => r.pontos > 0)
        .sort((x, y) => y.pontos - x.pontos);
    const chaves = indice.chaves
        .map((c) => ({ item: c, pontos: pontuar(tokens, [[c.nome, 2]]) }))
        .filter((r) => r.pontos > 0);
    const item = (r) => r.item;
    return {
        artigos: soOsMelhores(artigos).slice(0, 8).map(item),
        telas: soOsMelhores(telas).slice(0, 6).map(item),
        chaves: soOsMelhores(chaves).slice(0, 5).map(item),
    };
}

// ---------------------------------------------------------------- destaque do campo na tela aberta
function destacarCampo(nome) {
    if (!nome) {
        return;
    }
    const seletor = `.o_field_widget[name="${nome}"], div[name="${nome}"], [data-name="${nome}"]`;
    const aplicar = (el) => {
        el.classList.add("o_bt_destaque");
        el.scrollIntoView({ block: "center", behavior: "smooth" });
        setTimeout(() => el.classList.remove("o_bt_destaque"), 4000);
    };
    const ja = document.querySelector(seletor);
    if (ja) {
        aplicar(ja);
        return;
    }
    // A tela pode ser uma lista: destaca quando a pessoa abrir o registro (até 2 minutos)
    const observador = new MutationObserver(() => {
        const el = document.querySelector(seletor);
        if (el) {
            observador.disconnect();
            aplicar(el);
        }
    });
    observador.observe(document.body, { childList: true, subtree: true });
    setTimeout(() => observador.disconnect(), 120000);
}

// ---------------------------------------------------------------- serviço
export const ajudaService = {
    dependencies: ["action", "hotkey"],
    start(env, { action, hotkey }) {
        const estado = reactive({ aberto: false, indice: null, carregando: false, pedido: null });
        const ativo = Boolean(session.boteco_ajuda_rapida);

        async function carregar() {
            if (estado.indice || estado.carregando) {
                return;
            }
            estado.carregando = true;
            try {
                estado.indice = await rpc("/web/dataset/call_kw/boteco.ajuda.artigo/indice", {
                    model: "boteco.ajuda.artigo",
                    method: "indice",
                    args: [],
                    kwargs: {},
                });
            } finally {
                estado.carregando = false;
            }
        }

        const servico = {
            estado,
            ativo,
            abrir() {
                if (!ativo) {
                    window.open("/boteco/ajuda", "_blank", "noopener");
                    return;
                }
                estado.aberto = true;
                carregar();
            },
            fechar() {
                estado.aberto = false;
                estado.pedido = null;
            },
            /** Abre a ajuda já num artigo (ex.: botão "Ver ajuda" dos Primeiros passos). */
            abrirArtigo(codigo) {
                estado.pedido = codigo;
                servico.abrir();
            },
            alternar() {
                estado.aberto ? servico.fechar() : servico.abrir();
            },
            telaAtual() {
                const ctrl = action.currentController;
                return { xmlid: ctrl?.action?.xml_id || "", modelo: ctrl?.props?.resModel || ctrl?.action?.res_model || "" };
            },
            async abrirTela(alvo, campo) {
                servico.fechar();
                if (typeof alvo === "string" && alvo.includes(",") && !alvo.includes(".")) {
                    alvo = parseInt(alvo.split(",")[1], 10);
                }
                await action.doAction(alvo);
                destacarCampo(campo);
            },
            registrar(termo, achou, artigoId) {
                const { xmlid } = servico.telaAtual();
                rpc("/web/dataset/call_kw/boteco.ajuda.artigo/registrar_busca", {
                    model: "boteco.ajuda.artigo",
                    method: "registrar_busca",
                    args: [termo, achou, artigoId || false, xmlid],
                    kwargs: {},
                }).catch(() => {});
            },
            avaliar(artigoId, util) {
                return rpc("/web/dataset/call_kw/boteco.ajuda.artigo/avaliar", {
                    model: "boteco.ajuda.artigo",
                    method: "avaliar",
                    args: [artigoId, util],
                    kwargs: {},
                });
            },
        };

        if (ativo) {
            // F1 não está na lista de teclas do serviço de atalhos do Odoo: ouvimos direto no navegador
            window.addEventListener(
                "keydown",
                (ev) => {
                    if (ev.key === "F1") {
                        ev.preventDefault();
                        servico.alternar();
                    }
                },
                true
            );
            // Registrado depois do da paleta nativa: o atalho Ctrl+K passa a abrir a ajuda (que também acha telas)
            hotkey.add("control+k", () => servico.alternar(), { bypassEditableProtection: true, global: true });
        }
        return servico;
    },
};
registry.category("services").add("boteco_ajuda", ajudaService);

// ---------------------------------------------------------------- painel
export class AjudaPainel extends Component {
    static template = "boteco_base.AjudaPainel";
    static props = {};

    setup() {
        this.ajuda = useService("boteco_ajuda");
        this.estado = useState(this.ajuda.estado);
        this.state = useState({ consulta: "", artigoId: null, avaliado: {} });
        this.campo = useRef("busca");
        this._ultimaRegistrada = "";
        this._timer = null;
        useEffect(
            (aberto) => {
                if (aberto) {
                    this.focar();
                }
            },
            () => [this.estado.aberto]
        );
        onWillUnmount(() => clearTimeout(this._timer));
    }

    focar() {
        setTimeout(() => this.campo.el?.focus(), 50);
    }

    get indice() {
        return this.estado.indice || { artigos: [], telas: [], chaves: [] };
    }

    get artigo() {
        if (this.state.artigoId) {
            return this.indice.artigos.find((a) => a.id === this.state.artigoId);
        }
        return this.estado.pedido ? this.indice.artigos.find((a) => a.codigo === this.estado.pedido) : undefined;
    }

    get resultados() {
        return buscar(this.indice, this.state.consulta);
    }

    get daTela() {
        const { xmlid, modelo } = this.ajuda.telaAtual();
        return this.indice.artigos.filter((a) => a.telas.some((t) => t === xmlid || t === modelo)).slice(0, 4);
    }

    get maisProcurados() {
        return this.indice.artigos.slice(0, 6);
    }

    get relacionados() {
        const ids = this.artigo?.relacionados || [];
        return this.indice.artigos.filter((a) => ids.includes(a.id));
    }

    passosHtml(artigo) {
        return markup(artigo.passos || "");
    }

    aoDigitar(ev) {
        this.state.consulta = ev.target.value;
        this.state.artigoId = null;
        this.estado.pedido = null;
        clearTimeout(this._timer);
        // Registra a busca quando a pessoa para de digitar (para saber o que estão procurando)
        this._timer = setTimeout(() => {
            const termo = this.state.consulta.trim();
            if (termo.length >= 3 && termo !== this._ultimaRegistrada) {
                this._ultimaRegistrada = termo;
                const r = this.resultados;
                this.ajuda.registrar(termo, Boolean(r.artigos.length || r.telas.length), r.artigos[0]?.id);
            }
        }, 1500);
    }

    aoTeclar(ev) {
        if (ev.key === "Escape") {
            ev.preventDefault();
            if (this.state.artigoId) {
                this.state.artigoId = null;
            } else {
                this.ajuda.fechar();
            }
        } else if (ev.key === "Enter") {
            const r = this.resultados;
            if (r.artigos.length) {
                this.abrirArtigo(r.artigos[0]);
            } else if (r.telas.length) {
                this.ajuda.abrirTela(r.telas[0].acao);
            }
        }
    }

    abrirArtigo(artigo) {
        this.state.artigoId = artigo.id;
    }

    voltar() {
        this.state.artigoId = null;
        this.estado.pedido = null;
        this.focar();
    }

    async avaliar(util) {
        const id = this.artigo?.id;
        this.state.avaliado[id] = util ? "sim" : "nao";
        await this.ajuda.avaliar(id, util);
    }

    pedirAjuda() {
        const texto = encodeURIComponent(`Preciso de ajuda no sistema: ${this.state.consulta}`);
        window.open(`https://wa.me/?text=${texto}`, "_blank", "noopener");
    }
}

registry.category("main_components").add("boteco_base.AjudaPainel", { Component: AjudaPainel });
