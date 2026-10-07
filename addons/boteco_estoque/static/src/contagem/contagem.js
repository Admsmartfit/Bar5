/** @odoo-module ignore **/
/* Contagem de estoque no celular: lista grande, +/- e número; salva sozinho a cada 2 s. */
(function () {
    "use strict";
    const raiz = document.getElementById("bt-contagem");
    if (!raiz) {
        return;
    }
    const id = raiz.dataset.id;
    const lista = document.getElementById("bt-itens");
    const busca = document.getElementById("bt-busca");
    const progresso = document.getElementById("bt-progresso");
    const salvo = document.getElementById("bt-salvo");
    let linhas = [];
    const alteradas = {};
    let timer = null;

    async function chamar(rota, params) {
        const r = await fetch(rota, {
            method: "POST",
            credentials: "same-origin",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ jsonrpc: "2.0", method: "call", params }),
        });
        const dados = await r.json();
        if (dados.error) {
            throw new Error((dados.error.data && dados.error.data.message) || "Erro");
        }
        return dados.result;
    }

    function desenhar() {
        const termo = (busca.value || "").trim().toLowerCase();
        lista.innerHTML = "";
        for (const l of linhas) {
            if (termo && !l.produto.toLowerCase().includes(termo) && l.barcode !== termo) {
                continue;
            }
            const li = document.createElement("li");
            li.className = "bt-item" + (l.contada !== null && l.contada !== undefined ? " contado" : "");
            li.innerHTML =
                '<div class="bt-item__nome"></div><div class="bt-item__cat"></div>' +
                '<div class="bt-item__controles"><button type="button" data-d="-1">−</button>' +
                '<input type="number" inputmode="decimal" step="any" min="0"/>' +
                '<button type="button" data-d="1">+</button><span class="bt-item__un"></span></div>';
            li.querySelector(".bt-item__nome").textContent = l.produto;
            li.querySelector(".bt-item__cat").textContent = l.categoria || "";
            li.querySelector(".bt-item__un").textContent = l.unidade || "";
            const campo = li.querySelector("input");
            campo.value = l.contada === null || l.contada === undefined ? "" : l.contada;
            campo.addEventListener("input", () => marcar(l, campo.value === "" ? null : parseFloat(campo.value), li));
            li.querySelectorAll("button").forEach((b) =>
                b.addEventListener("click", () => {
                    const atual = parseFloat(campo.value || "0") || 0;
                    const novo = Math.max(0, atual + parseFloat(b.dataset.d));
                    campo.value = novo;
                    marcar(l, novo, li);
                })
            );
            lista.appendChild(li);
        }
        const feitas = linhas.filter((l) => l.contada !== null && l.contada !== undefined).length;
        progresso.textContent = `${feitas} de ${linhas.length} contados`;
    }

    function marcar(linha, valor, li) {
        linha.contada = valor;
        alteradas[linha.id] = valor === null ? "" : valor;
        li.classList.toggle("contado", valor !== null);
        salvo.textContent = "salvando…";
        clearTimeout(timer);
        timer = setTimeout(salvar, 2000);
    }

    async function salvar(terminar = false) {
        const enviar = { ...alteradas };
        for (const k of Object.keys(enviar)) {
            delete alteradas[k];
        }
        try {
            await chamar(`/boteco/contagem/${id}/salvar`, { contagens: enviar, terminar });
            salvo.textContent = "salvo ✓";
        } catch (e) {
            Object.assign(alteradas, enviar);
            salvo.textContent = "sem conexão – tento de novo";
            timer = setTimeout(salvar, 5000);
        }
    }

    document.getElementById("bt-terminar").addEventListener("click", async () => {
        clearTimeout(timer);
        await salvar(true);
        window.location.href = "/odoo/action-boteco_estoque.action_boteco_contagem";
    });
    busca.addEventListener("input", desenhar);

    chamar(`/boteco/contagem/${id}/dados`, {}).then((dados) => {
        linhas = dados.linhas;
        desenhar();
    });
})();
