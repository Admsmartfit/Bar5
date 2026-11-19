/** @odoo-module ignore **/
/* Tela de entrada por PIN. JavaScript puro (sem framework) para abrir rápido em tablet velho. */
(function () {
    "use strict";

    const MIN = 4;
    const MAX = 6;
    const pessoas = document.getElementById("bt-pessoas");
    const teclado = document.getElementById("bt-teclado");
    if (!pessoas || !teclado) {
        return;
    }
    const pontos = document.getElementById("bt-pontos");
    const erro = document.getElementById("bt-erro");
    const nomeEscolhido = document.getElementById("bt-nome-escolhido");
    const relogio = document.getElementById("bt-relogio");

    let pessoaId = null;
    let pin = "";
    let enviando = false;

    function atualizarRelogio() {
        const agora = new Date();
        relogio.textContent = agora.toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit" });
    }
    atualizarRelogio();
    setInterval(atualizarRelogio, 15000);

    function desenharPontos() {
        pontos.querySelectorAll("span").forEach((el, i) => {
            el.classList.toggle("cheio", i < pin.length);
            el.hidden = i >= Math.max(MIN, pin.length);
        });
    }

    function mostrarTeclado(botao) {
        pessoaId = parseInt(botao.dataset.id, 10);
        nomeEscolhido.textContent = "Olá, " + botao.dataset.nome.split(" ")[0] + "! Digite seu PIN";
        pin = "";
        erro.textContent = "";
        desenharPontos();
        pessoas.hidden = true;
        teclado.hidden = false;
    }

    function voltar() {
        pessoaId = null;
        pin = "";
        // Sai do modo "gerente desbloqueia", se estava nele
        if (modoGerente) {
            modoGerente = false;
            tituloNome.textContent = nomeOriginal;
        }
        mostrarDesbloquear(false);
        erro.textContent = "";
        teclado.hidden = true;
        pessoas.hidden = false;
    }

    function tremer(mensagem) {
        erro.textContent = mensagem;
        pontos.classList.remove("tremer");
        void pontos.offsetWidth; // reinicia a animação
        pontos.classList.add("tremer");
        try {
            navigator.vibrate?.(200);
        } catch {
            // sem vibração
        }
        pin = "";
        desenharPontos();
    }

    // Modo "gerente desbloqueia": o mesmo teclado recebe o PIN do gerente
    let modoGerente = false;
    const botaoDesbloquear = document.getElementById("bt-desbloquear");
    const tituloNome = document.getElementById("bt-nome-escolhido");
    let nomeOriginal = "";

    function mostrarDesbloquear(mostrar) {
        if (botaoDesbloquear) {
            botaoDesbloquear.hidden = !mostrar;
        }
    }

    botaoDesbloquear?.addEventListener("click", () => {
        modoGerente = true;
        nomeOriginal = tituloNome.textContent;
        tituloNome.textContent = "PIN do gerente";
        erro.textContent = "O gerente digita o PIN dele para liberar " + nomeOriginal + ".";
        mostrarDesbloquear(false);
        pin = "";
        desenharPontos();
    });

    async function desbloquear() {
        enviando = true;
        try {
            const resposta = await fetch("/boteco/pin/desbloquear", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                credentials: "same-origin",
                body: JSON.stringify({ jsonrpc: "2.0", method: "call", params: { user_id: pessoaId, pin_gerente: pin } }),
            });
            const resultado = (await resposta.json()).result || {};
            if (resultado.ok) {
                modoGerente = false;
                tituloNome.textContent = nomeOriginal;
                pin = "";
                desenharPontos();
                erro.textContent = resultado.mensagem;
                return;
            }
            tremer(resultado.erro || "Não deu certo.");
        } catch (e) {
            tremer("Sem conexão com o servidor. Confira o Wi-Fi e tente de novo.");
        } finally {
            enviando = false;
        }
    }

    async function entrar() {
        if (enviando) {
            return;
        }
        if (modoGerente) {
            if (pin.length < MIN) {
                tremer("O PIN tem de 4 a 6 números.");
                return;
            }
            return desbloquear();
        }
        if (pin.length < MIN) {
            tremer("O PIN tem de 4 a 6 números.");
            return;
        }
        enviando = true;
        erro.textContent = "Entrando…";
        try {
            const resposta = await fetch("/boteco/pin/entrar", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                credentials: "same-origin",
                body: JSON.stringify({
                    jsonrpc: "2.0",
                    method: "call",
                    params: { user_id: pessoaId, pin: pin },
                }),
            });
            const dados = await resposta.json();
            const resultado = dados.result || {};
            if (resultado.ok) {
                window.location.assign(resultado.url || "/boteco/inicio");
                return;
            }
            const mensagem = resultado.erro || (dados.error && dados.error.data && dados.error.data.message) || "Não deu certo. Tente de novo.";
            tremer(mensagem);
            mostrarDesbloquear(/bloquead/i.test(mensagem));
        } catch (e) {
            tremer("Sem conexão com o servidor. Confira o Wi-Fi e tente de novo.");
        } finally {
            enviando = false;
        }
    }

    function tecla(valor) {
        if (valor === "apagar") {
            pin = pin.slice(0, -1);
            erro.textContent = "";
        } else if (valor === "ok") {
            entrar();
            return;
        } else if (pin.length < MAX) {
            pin += valor;
        }
        desenharPontos();
    }

    pessoas.addEventListener("click", (ev) => {
        const botao = ev.target.closest(".bt-pessoa");
        if (botao) {
            mostrarTeclado(botao);
        }
    });
    teclado.addEventListener("click", (ev) => {
        const botao = ev.target.closest(".bt-tecla");
        if (botao) {
            tecla(botao.dataset.tecla);
        }
    });
    document.getElementById("bt-voltar").addEventListener("click", voltar);
    document.addEventListener("keydown", (ev) => {
        if (teclado.hidden) {
            return;
        }
        if (/^[0-9]$/.test(ev.key)) {
            tecla(ev.key);
        } else if (ev.key === "Backspace") {
            tecla("apagar");
        } else if (ev.key === "Enter") {
            tecla("ok");
        } else if (ev.key === "Escape") {
            voltar();
        }
    });
})();
