// Gera as fotos de tela dos artigos da ajuda rápida (Etapa 26) em addons/boteco_base/static/ajuda/<codigo>.png
//
//   node scripts/dev/gerar_capturas_ajuda.mjs https://localhost admin SENHA [codigo ...]
//
// Abre cada artigo que tem "Abrir esta tela", destaca o campo (se houver) e fotografa em tema claro, letra normal.
// Rode no desenvolvimento antes de cada versão e faça commit das imagens.
// Usa o Chrome DevTools Protocol direto (WebSocket nativo do Node 22+), sem dependências.
import { spawn } from "node:child_process";
import { mkdtempSync, mkdirSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const [base = "https://localhost", login = "admin", senha = "admin", ...somente] = process.argv.slice(2);
const DESTINO = join(dirname(fileURLToPath(import.meta.url)), "..", "..", "addons", "boteco_base", "static", "ajuda");
mkdirSync(DESTINO, { recursive: true });

const CHROMES = [
    process.env.CHROME,
    "C:/Program Files/Google/Chrome/Application/chrome.exe",
    "C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe",
    "/usr/bin/chromium",
    "/usr/bin/google-chrome",
].filter(Boolean);
const espera = (ms) => new Promise((r) => setTimeout(r, ms));
const porta = 9400 + Math.floor(Math.random() * 400);
const perfil = mkdtempSync(join(tmpdir(), "boteco-capturas-"));
let chrome;
for (const exe of CHROMES) {
    try {
        chrome = spawn(exe, ["--headless=new", `--remote-debugging-port=${porta}`, "--ignore-certificate-errors",
            "--no-first-run", "--disable-gpu", `--user-data-dir=${perfil}`, "--window-size=1366,768", "about:blank"],
            { stdio: "ignore" });
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
            // subindo
        }
        await espera(200);
    }
    throw new Error("Chrome não respondeu");
}
const ws = new WebSocket(await alvo());
await new Promise((r) => ws.addEventListener("open", r));
let seq = 0;
const pendentes = new Map();
ws.addEventListener("message", (ev) => {
    const msg = JSON.parse(ev.data);
    if (msg.id && pendentes.has(msg.id)) {
        pendentes.get(msg.id)(msg);
        pendentes.delete(msg.id);
    }
});
const cdp = (method, params = {}) =>
    new Promise((resolve) => {
        const id = ++seq;
        pendentes.set(id, resolve);
        ws.send(JSON.stringify({ id, method, params }));
    });
const avaliar = async (expr) =>
    (await cdp("Runtime.evaluate", { expression: expr, awaitPromise: true, returnByValue: true })).result?.result?.value;
const chamar = (model, method, args) =>
    avaliar(`fetch('/web/dataset/call_kw', {method: 'POST', headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({jsonrpc: '2.0', method: 'call', params: {model: ${JSON.stringify(model)},
        method: ${JSON.stringify(method)}, args: ${JSON.stringify(args)}, kwargs: {}}})}).then(r => r.json()).then(j => j.result)`);

await cdp("Page.enable");
await cdp("Emulation.setDeviceMetricsOverride", { width: 1366, height: 768, deviceScaleFactor: 1, mobile: false });
await cdp("Page.navigate", { url: `${base}/web/login` });
await espera(8000);
await avaliar(`(() => { document.querySelector('input[name=login]').value = ${JSON.stringify(login)};
    document.querySelector('input[name=password]').value = ${JSON.stringify(senha)}; document.querySelector('form').submit(); })()`);
await espera(9000);
await cdp("Page.navigate", { url: `${base}/odoo` });
await espera(10000);

const uid = await avaliar(`fetch('/web/session/get_session_info', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: '{}'})
    .then(r => r.json()).then(j => j.result.uid)`);
if (!uid) {
    console.error("Não consegui entrar: confira usuário e senha.");
    process.exit(1);
}
// Tema claro e letra normal só durante as fotos; no fim, devolve o que a pessoa usava
const antes = (await chamar("res.users", "read", [[uid], ["boteco_tema", "boteco_tamanho_fonte", "boteco_cor_destaque", "boteco_alto_contraste"]]))[0];
await chamar("res.users", "write", [[uid], { boteco_tema: "claro", boteco_tamanho_fonte: "normal", boteco_cor_destaque: "roxo", boteco_alto_contraste: true }]);

const indice = await chamar("boteco.ajuda.artigo", "indice", []);
let feitas = 0;
for (const art of indice.artigos) {
    if (!art.acao || (somente.length && !somente.includes(art.codigo))) {
        continue;
    }
    await cdp("Page.navigate", { url: `${base}/odoo/action-${art.acao}` });
    await espera(7000);
    if (art.destacar) {
        const temCampo = await avaliar(`!!document.querySelector('.o_field_widget[name="${art.destacar}"]')`);
        if (!temCampo) {
            await avaliar(`document.querySelector('.o_list_button_add, .o-kanban-button-new')?.click()`);
            await espera(3500);
        }
        await avaliar(`(() => { const el = document.querySelector('.o_field_widget[name="${art.destacar}"]');
            if (el) { el.style.outline = '3px solid #ea580c'; el.style.outlineOffset = '2px'; el.scrollIntoView({block: 'center'}); } })()`);
        await espera(600);
    }
    const r = await cdp("Page.captureScreenshot", { format: "png" });
    if (r.result?.data) {
        writeFileSync(join(DESTINO, `${art.codigo}.png`), Buffer.from(r.result.data, "base64"));
        feitas++;
        console.log("foto:", art.codigo);
    }
}
await chamar("res.users", "write", [[uid], antes]);
console.log(`${feitas} foto(s) em ${DESTINO}`);
ws.close();
chrome.kill();
process.exit(0);
