// Abre as telas do Boteco num Chrome headless e lista erros de JavaScript.
//
//   node scripts/dev/verificar_telas.mjs https://localhost admin SENHA /pos/ui?config_id=1 [/outra/url ...]
//
// Usa o Chrome DevTools Protocol direto (WebSocket nativo do Node 22+), sem dependências.
import { spawn } from "node:child_process";
import { mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

const [base = "https://localhost", login = "admin", senha = "admin", ...caminhos] = process.argv.slice(2);
const CHROMES = [
    process.env.CHROME,
    "C:/Program Files/Google/Chrome/Application/chrome.exe",
    "C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe",
    "/usr/bin/chromium",
    "/usr/bin/google-chrome",
].filter(Boolean);

const espera = (ms) => new Promise((r) => setTimeout(r, ms));
const porta = 9333 + Math.floor(Math.random() * 500);
const perfil = mkdtempSync(join(tmpdir(), "boteco-chrome-"));
let chrome;
for (const exe of CHROMES) {
    try {
        chrome = spawn(exe, [
            "--headless=new", `--remote-debugging-port=${porta}`, "--ignore-certificate-errors",
            "--no-first-run", "--disable-gpu", `--user-data-dir=${perfil}`, "--window-size=1280,900", "about:blank",
        ], { stdio: "ignore" });
        break;
    } catch {
        // tenta o próximo
    }
}

async function alvo() {
    for (let i = 0; i < 50; i++) {
        try {
            const lista = await (await fetch(`http://127.0.0.1:${porta}/json/list`)).json();
            const pagina = lista.find((t) => t.type === "page");
            if (pagina) {
                return pagina.webSocketDebuggerUrl;
            }
        } catch {
            // ainda subindo
        }
        await espera(200);
    }
    throw new Error("Chrome não respondeu");
}

const ws = new WebSocket(await alvo());
await new Promise((r) => ws.addEventListener("open", r));
let seq = 0;
const pendentes = new Map();
const erros = [];
ws.addEventListener("message", (ev) => {
    const msg = JSON.parse(ev.data);
    if (msg.id && pendentes.has(msg.id)) {
        pendentes.get(msg.id)(msg);
        pendentes.delete(msg.id);
        return;
    }
    if (msg.method === "Runtime.exceptionThrown") {
        const d = msg.params.exceptionDetails;
        erros.push(`[exceção] ${d.exception?.description || d.text}`.slice(0, 1500));
    } else if (msg.method === "Runtime.consoleAPICalled" && msg.params.type === "error") {
        erros.push("[console] " + msg.params.args.map((a) => a.value ?? a.description ?? "").join(" ").slice(0, 1500));
    } else if (msg.method === "Log.entryAdded" && msg.params.entry.level === "error") {
        erros.push(`[log] ${msg.params.entry.text} ${msg.params.entry.url || ""}`.slice(0, 600));
    }
});
const cdp = (method, params = {}) =>
    new Promise((resolve) => {
        const id = ++seq;
        pendentes.set(id, resolve);
        ws.send(JSON.stringify({ id, method, params }));
    });
const avaliar = async (expressao) => (await cdp("Runtime.evaluate", { expression: expressao, awaitPromise: true, returnByValue: true })).result?.result?.value;

await cdp("Runtime.enable");
await cdp("Log.enable");
await cdp("Page.enable");

async function abrir(url, segundos = 12) {
    await cdp("Page.navigate", { url });
    await espera(segundos * 1000);
}

await abrir(`${base}/web/login`, 4);
await avaliar(`(() => {
    document.querySelector('input[name=login]').value = ${JSON.stringify(login)};
    document.querySelector('input[name=password]').value = ${JSON.stringify(senha)};
    document.querySelector('form').submit();
})()`);
await espera(6000);

let falhou = false;
for (const caminho of caminhos.length ? caminhos : ["/odoo"]) {
    erros.length = 0;
    if (caminho.startsWith("js:")) {
        // Ação na página atual (clicar, digitar...). Ex.: "js:document.querySelector('.btn').click()"
        const retorno = await avaliar(`(async () => { ${caminho.slice(3)} })()`);
        await espera(4000);
        if (retorno !== undefined) {
            console.log("retorno:", JSON.stringify(retorno));
        }
    } else {
        await abrir(base + caminho, 18);
    }
    const resumo = await avaliar(`(() => ({
        titulo: document.title,
        url: location.pathname + location.search,
        erroOdoo: [...document.querySelectorAll('.o_error_dialog, .o_dialog_error, .modal-body pre')].map(e => e.innerText.slice(0, 800)),
        tamanho: document.body.innerText.length,
        texto: document.body.innerText.slice(0, 300).replace(/\\s+/g, ' '),
    }))()`);
    console.log(`\n=== ${caminho}`);
    console.log(JSON.stringify(resumo, null, 1));
    const relevantes = erros.filter((e) => !/favicon|ERR_CERT|Failed to load resource.*404/.test(e));
    if (relevantes.length || resumo?.erroOdoo?.length) {
        falhou = true;
        console.log("ERROS:");
        for (const e of relevantes) {
            console.log(" -", e);
        }
    } else {
        console.log("sem erros de JavaScript");
    }
}

ws.close();
chrome.kill();
process.exit(falhou ? 1 : 0);
