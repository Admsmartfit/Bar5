/** @odoo-module **/
// Primeiros passos: assistente de 5 etapas em tela cheia na 1ª entrada do dono (meta: 1º pedido de teste em
// menos de 15 min) + lista persistente que se marca sozinha. Cada etapa pode ser pulada (fica pendente na lista).

import { Component, onMounted, onPatched, onWillStart, onWillUnmount, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";

export class PrimeirosPassos extends Component {
    static template = "boteco_base.PrimeirosPassos";
    static props = ["*"];

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.ajuda = useService("boteco_ajuda");
        this.notification = useService("notification");
        this.state = useState({
            dados: null, telaAssistente: 1, ocupado: false, w: null,
            emp: {}, op: { atendimento: ["garcom"], producao_lote: false, ambientes: [] },
            equipe: [], msg: {}, ips: {}, testes: {},
        });
        onWillStart(() => this.carregar());
        // Tela cheia durante o assistente: some a barra do Odoo (menos distração)
        const telaCheia = () => document.body.classList.toggle("o_bt_pp_tela_cheia", Boolean(this.state.dados?.assistente));
        onMounted(telaCheia);
        onPatched(telaCheia);
        onWillUnmount(() => document.body.classList.remove("o_bt_pp_tela_cheia"));
    }

    async carregar() {
        const dados = await this.orm.call("boteco.implantacao", "estado", []);
        this.state.dados = dados;
        if (dados.assistente) {
            await this.carregarAssistente();
        }
    }

    async carregarAssistente() {
        const w = await this.orm.call("boteco.implantacao", "assistente_dados", []);
        this.aplicarAssistente(w);
        this.state.emp = { ...w.empresa, logo: null };
        this.state.op = {
            atendimento: [...w.operacao.atendimento],
            producao_lote: w.operacao.producao_lote,
            ambientes: w.operacao.ambientes.length
                ? w.operacao.ambientes.map((a) => ({ ...a, lugares: 4, existente: true }))
                : [{ nome: "Salão", mesas: 10, lugares: 4 }],
        };
        this.state.equipe = [
            { nome: "", perfil: "gerente", pin: "" },
            { nome: "", perfil: "garcom", pin: "" },
        ];
    }

    aplicarAssistente(w) {
        this.state.w = w;
        for (const s of w.setores) {
            if (!(s.id in this.state.ips)) {
                this.state.ips[s.id] = s.ip;
            }
        }
    }

    get progresso() {
        const d = this.state.dados;
        return d && d.total ? Math.round((d.feitos / d.total) * 100) : 0;
    }

    /** Obrigatórios que ainda faltam (atalhos no topo da tela). */
    get faltando() {
        const d = this.state.dados;
        return d ? d.fases.filter((f) => f.codigo !== "depois").flatMap((f) => f.passos)
            .filter((p) => p.obrigatorio && p.situacao !== "feito") : [];
    }

    irPara(passo) {
        const el = document.getElementById("bt-passo-" + passo.codigo);
        el?.scrollIntoView({ behavior: "smooth", block: "center" });
        el?.classList.add("o_bt_pp__destaque");
        setTimeout(() => el?.classList.remove("o_bt_pp__destaque"), 2000);
    }

    icone(passo) {
        return { feito: "fa-check-circle text-success", pulado: "fa-forward text-muted" }[passo.situacao] ||
            (passo.obrigatorio ? "fa-circle-o text-warning" : "fa-circle-o text-muted");
    }

    // ---------------------------------------------------------------- assistente (5 etapas)
    get etapas() {
        return ["Sua empresa", "Como você atende", "Cardápio", "Impressoras", "Equipe e teste"];
    }

    async rodar(funcao) {
        // Um botão por vez; erro aparece como aviso (nunca trava a tela)
        if (this.state.ocupado) {
            return;
        }
        this.state.ocupado = true;
        try {
            return await funcao();
        } catch (erro) {
            this.notification.add(erro?.data?.message || String(erro), { type: "danger" });
        } finally {
            this.state.ocupado = false;
        }
    }

    irTela(n) {
        this.state.telaAssistente = n;
        if (n === 3) {
            this.rodar(async () => this.aplicarAssistente(await this.orm.call("boteco.implantacao", "preparar_cardapio", [])));
        }
    }

    pular() {
        this.irTela(this.state.telaAssistente + 1);
    }

    voltarTela() {
        this.irTela(Math.max(1, this.state.telaAssistente - 1));
    }

    concluiuEtapa() {
        confete();
        this.irTela(this.state.telaAssistente + 1);
    }

    // Etapa 1 -------------------------------------------------------------
    async buscarCnpj() {
        this.state.msg.cnpj = "Buscando…";
        const r = await this.rodar(() => this.orm.call("boteco.implantacao", "buscar_cnpj", [this.state.emp.cnpj]));
        if (!r || r.erro) {
            this.state.msg.cnpj = r?.erro || "Não deu certo. Preencha à mão.";
            return;
        }
        for (const [chave, valor] of Object.entries(r)) {
            if (valor) {
                this.state.emp[chave] = valor;
            }
        }
        this.state.msg.cnpj = "Pronto! Confira os dados abaixo.";
    }

    async buscarCep() {
        this.state.msg.cep = "Buscando…";
        const r = await this.rodar(() => this.orm.call("boteco.implantacao", "buscar_cep", [this.state.emp.cep]));
        if (!r || r.erro) {
            this.state.msg.cep = r?.erro || "Não deu certo. Preencha à mão.";
            return;
        }
        Object.assign(this.state.emp, Object.fromEntries(Object.entries(r).filter(([, v]) => v)));
        this.state.msg.cep = "";
    }

    escolherLogo(ev) {
        const arquivo = ev.target.files?.[0];
        if (!arquivo) {
            return;
        }
        const leitor = new FileReader();
        leitor.onload = () => (this.state.emp.logo = leitor.result);
        leitor.readAsDataURL(arquivo);
    }

    async salvarIdentidade() {
        const w = await this.rodar(() => this.orm.call("boteco.implantacao", "salvar_identidade", [this.state.emp]));
        if (w) {
            this.aplicarAssistente(w);
            this.concluiuEtapa();
        }
    }

    // Etapa 2 -------------------------------------------------------------
    alternarAtendimento(modo) {
        const lista = this.state.op.atendimento;
        const i = lista.indexOf(modo);
        if (i >= 0) {
            lista.splice(i, 1);
        } else {
            lista.push(modo);
        }
    }

    adicionarAmbiente() {
        this.state.op.ambientes.push({ nome: "", mesas: 6, lugares: 4 });
    }

    removerAmbiente(i) {
        this.state.op.ambientes.splice(i, 1);
    }

    async salvarOperacao() {
        const w = await this.rodar(() => this.orm.call("boteco.implantacao", "salvar_operacao", [this.state.op]));
        if (w) {
            this.aplicarAssistente(w);
            if (w.mesas_criadas) {
                this.notification.add(`${w.mesas_criadas} mesa(s) criada(s) no mapa do salão.`, { type: "success" });
            }
            this.concluiuEtapa();
        }
    }

    // Etapa 3 -------------------------------------------------------------
    async importarPlanilha() {
        // Abre a planilha numa janela por cima, sem sair do assistente
        await this.action.doAction("boteco_cardapio.action_boteco_cardapio_planilha", {
            onClose: () => this.rodar(async () => this.aplicarAssistente(await this.orm.call("boteco.implantacao", "assistente_dados", []))),
        });
    }

    async alternarHappy() {
        const w = await this.rodar(() =>
            this.orm.call("boteco.implantacao", "ligar_happy_hour", [!this.state.w.cardapio.happy_hour])
        );
        if (w) {
            this.aplicarAssistente(w);
        }
    }

    // Etapa 4 -------------------------------------------------------------
    async salvarImpressora(setor) {
        const w = await this.rodar(() => this.orm.call("boteco.implantacao", "salvar_impressora", [setor.id, this.state.ips[setor.id]]));
        if (w) {
            this.aplicarAssistente(w);
            await this.testarImpressora(w.setores.find((s) => s.id === setor.id));
        }
    }

    async testarImpressora(setor) {
        if (!setor?.impressora_id) {
            return;
        }
        this.state.testes[setor.id] = { mensagem: "Imprimindo…" };
        const r = await this.rodar(() => this.orm.call("boteco.implantacao", "testar_impressora", [setor.impressora_id]));
        this.state.testes[setor.id] = r || { ok: false, mensagem: "Não deu certo." };
        if (r?.ok) {
            confete();
        }
    }

    // Etapa 5 -------------------------------------------------------------
    adicionarPessoa() {
        this.state.equipe.push({ nome: "", perfil: "garcom", pin: "" });
    }

    async salvarEquipe() {
        const r = await this.rodar(() => this.orm.call("boteco.implantacao", "criar_equipe", [this.state.equipe]));
        if (!r) {
            return;
        }
        this.aplicarAssistente(r);
        if (r.erros.length) {
            this.state.msg.equipe = r.erros.map((e) => `Linha ${e.linha + 1}: ${e.erro}`).join(" · ");
            return;
        }
        this.state.msg.equipe = "";
        this.state.equipe = [];
        confete();
    }

    async ligarTreino() {
        const r = await this.rodar(() => this.orm.call("boteco.implantacao", "ligar_treino", []));
        if (r) {
            this.state.msg.treino = r.mensagem;
        }
    }

    async concluirAssistente() {
        await this.rodar(async () => {
            this.state.dados = await this.orm.call("boteco.implantacao", "salvar_assistente", [{}]);
        });
        confete();
    }

    async reabrirAssistente() {
        await this.orm.call("boteco.implantacao", "reabrir_assistente", []);
        this.state.telaAssistente = 1;
        await this.carregar();
    }

    // ---------------------------------------------------------------- lista
    async fazer(passo) {
        const acao = await this.orm.call("boteco.implantacao", "acao", [passo.codigo]);
        // Janela (ex.: Wi-Fi): ao fechar, a lista se atualiza e o passo aparece como feito
        await this.action.doAction(acao, { onClose: () => this.carregar() });
    }

    verAjuda(passo) {
        this.ajuda.abrirArtigo(passo.artigo);
    }

    async marcar(passo, situacao) {
        this.state.dados = await this.orm.call("boteco.implantacao", "marcar", [passo.codigo, situacao]);
    }

    async abrirCasa() {
        const d = this.state.dados;
        let forcar = false;
        if (d.faltam) {
            forcar = window.confirm(
                `Ainda faltam ${d.faltam} passo(s) obrigatório(s). Abrir a casa mesmo assim? (fica registrado na auditoria)`
            );
            if (!forcar) {
                return;
            }
        }
        await this.orm.call("boteco.implantacao", "concluir", [forcar]);
        this.notification.add("Casa aberta! 🎉 Bom trabalho. A lista continua em Início › Primeiros passos.", {
            type: "success",
        });
        await this.carregar();
    }
}

/** Confete leve ao concluir uma etapa (some sozinho; quem pediu menos movimento não vê). */
export function confete() {
    if (window.matchMedia?.("(prefers-reduced-motion: reduce)").matches) {
        return;
    }
    const caixa = document.createElement("div");
    caixa.className = "o_bt_confete";
    const cores = ["#16a34a", "#f59e0b", "#2563eb", "#dc2626", "#a855f7", "#facc15"];
    for (let i = 0; i < 40; i++) {
        const p = document.createElement("span");
        p.style.left = `${Math.random() * 100}%`;
        p.style.background = cores[i % cores.length];
        p.style.animationDelay = `${Math.random() * 0.3}s`;
        p.style.transform = `rotate(${Math.random() * 360}deg)`;
        caixa.appendChild(p);
    }
    document.body.appendChild(caixa);
    setTimeout(() => caixa.remove(), 1800);
}

registry.category("actions").add("boteco_base.primeiros_passos", PrimeirosPassos);
