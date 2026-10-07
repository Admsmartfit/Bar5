/** @odoo-module ignore **/
/* Separação lendo o QR da etiqueta: leitor USB/Bluetooth (digita + Enter) ou câmera (BarcodeDetector). */
(function () {
    "use strict";
    const raiz = document.getElementById("bt-separacao");
    if (!raiz) {
        return;
    }
    const id = raiz.dataset.id;
    const campo = document.getElementById("bt-codigo");
    const msg = document.getElementById("bt-msg");
    const lista = document.getElementById("bt-itens");
    const video = document.getElementById("bt-video");

    async function chamar(rota, params) {
        const r = await fetch(rota, {
            method: "POST",
            credentials: "same-origin",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ jsonrpc: "2.0", method: "call", params: params || {} }),
        });
        const dados = await r.json();
        if (dados.error) {
            throw new Error((dados.error.data && dados.error.data.message) || "Erro");
        }
        return dados.result;
    }

    function avisar(texto, ok) {
        msg.textContent = texto;
        msg.dataset.ok = ok ? "1" : "0";
        if (navigator.vibrate) {
            navigator.vibrate(ok ? 80 : [200, 80, 200]);
        }
    }

    function desenhar(dados) {
        lista.innerHTML = "";
        for (const item of dados.itens || []) {
            const li = document.createElement("li");
            const completo = item.separado >= item.pedido;
            li.className = "bt-item" + (completo ? " completo" : "");
            const titulo = document.createElement("div");
            titulo.className = "bt-item__nome";
            titulo.textContent = `${item.produto}: ${item.separado} de ${item.pedido} ${item.unidade}`;
            li.appendChild(titulo);
            for (const l of item.lotes) {
                const d = document.createElement("div");
                d.className = "bt-item__lote";
                d.textContent = `Lote ${l.lote} · ${l.quantidade} · validade ${l.validade}`;
                li.appendChild(d);
            }
            lista.appendChild(li);
        }
    }

    async function ler(codigo) {
        codigo = (codigo || "").trim();
        if (!codigo) {
            return;
        }
        try {
            const r = await chamar(`/boteco/separacao/${id}/ler`, { codigo });
            avisar(r.mensagem, r.ok);
            desenhar(r);
        } catch (e) {
            avisar("Sem conexão. Tente de novo.", false);
        }
    }

    campo.addEventListener("keydown", (ev) => {
        if (ev.key === "Enter") {
            ler(campo.value);
            campo.value = "";
        }
    });

    document.getElementById("bt-camera").addEventListener("click", async () => {
        if (!("BarcodeDetector" in window)) {
            avisar("Este navegador não lê QR pela câmera. Use o leitor ou digite o código.", false);
            return;
        }
        const detector = new window.BarcodeDetector({ formats: ["qr_code"] });
        const stream = await navigator.mediaDevices.getUserMedia({ video: { facingMode: "environment" } });
        video.srcObject = stream;
        video.hidden = false;
        await video.play();
        let ultimo = "";
        const loop = async () => {
            if (video.hidden) {
                return;
            }
            try {
                const achados = await detector.detect(video);
                const valor = achados[0] && achados[0].rawValue;
                if (valor && valor !== ultimo) {
                    ultimo = valor;
                    await ler(valor);
                    setTimeout(() => (ultimo = ""), 2000);
                }
            } catch (e) {
                // continua tentando
            }
            requestAnimationFrame(loop);
        };
        loop();
    });

    document.getElementById("bt-concluir").addEventListener("click", async () => {
        const r = await chamar(`/boteco/separacao/${id}/concluir`);
        avisar(r.mensagem, r.ok);
        if (r.ok) {
            video.hidden = true;
            const stream = video.srcObject;
            if (stream) {
                stream.getTracks().forEach((t) => t.stop());
            }
        }
    });

    chamar(`/boteco/separacao/${id}/dados`).then(desenhar);
})();
