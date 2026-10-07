/** @odoo-module */
// Funções puras do salão (espelham boteco_pos/models/utils.py).

/** Divide o total em partes que somam exatamente o total (centavos vão para as primeiras). */
export function dividirEmPartes(total, partes, casas = 2) {
    const n = Math.max(parseInt(partes || 1, 10), 1);
    const fator = 10 ** casas;
    const totalCentavos = Math.round(total * fator);
    const base = Math.floor(totalCentavos / n);
    const resto = totalCentavos - base * n;
    return Array.from({ length: n }, (_v, i) => (base + (i < resto ? 1 : 0)) / fator);
}

export function soDigitos(texto) {
    return String(texto || "").replace(/\D/g, "");
}

export function cpfValido(cpf) {
    const d = soDigitos(cpf);
    if (d.length !== 11 || /^(\d)\1+$/.test(d)) {
        return false;
    }
    for (const tamanho of [9, 10]) {
        let soma = 0;
        for (let i = 0; i < tamanho; i++) {
            soma += parseInt(d[i], 10) * (tamanho + 1 - i);
        }
        if (((soma * 10) % 11) % 10 !== parseInt(d[tamanho], 10)) {
            return false;
        }
    }
    return true;
}

export function cnpjValido(cnpj) {
    const d = soDigitos(cnpj);
    if (d.length !== 14 || /^(\d)\1+$/.test(d)) {
        return false;
    }
    const pesos1 = [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2];
    const pesos2 = [6, ...pesos1];
    for (const [pesos, pos] of [[pesos1, 12], [pesos2, 13]]) {
        const soma = pesos.reduce((acc, p, i) => acc + parseInt(d[i], 10) * p, 0);
        let digito = 11 - (soma % 11);
        digito = digito >= 10 ? 0 : digito;
        if (digito !== parseInt(d[pos], 10)) {
            return false;
        }
    }
    return true;
}

export function documentoValido(doc) {
    const d = soDigitos(doc);
    return d.length === 11 ? cpfValido(d) : d.length === 14 ? cnpjValido(d) : false;
}

/** Quantidade da linha que já foi para a produção (pela tela ou pelo servidor). */
export function qtdEnviada(order, line) {
    let naTela = 0;
    const linhas = order?.last_order_preparation_change?.lines || {};
    for (const mudanca of Object.values(linhas)) {
        if (mudanca.uuid === line.uuid) {
            naTela += mudanca.quantity || 0;
        }
    }
    return Math.max(naTela, line.boteco_qtd_enviada || 0);
}

const sons = {};
export function tocarSom(nome = "bell") {
    try {
        sons[nome] = sons[nome] || new Audio(`/point_of_sale/static/src/sounds/${nome}.mp3`);
        sons[nome].currentTime = 0;
        sons[nome].play().catch(() => {});
    } catch {
        // Navegador sem áudio: segue sem som
    }
}

/** Minutos desde uma data UTC "YYYY-MM-DD HH:MM:SS" (formato do servidor). */
export function minutosDesde(textoUtc, agora = Date.now()) {
    if (!textoUtc) {
        return null;
    }
    const instante = Date.parse(String(textoUtc).replace(" ", "T") + "Z");
    if (Number.isNaN(instante)) {
        return null;
    }
    return Math.max(0, Math.floor((agora - instante) / 60000));
}
