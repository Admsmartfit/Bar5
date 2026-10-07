"""Funções puras usadas pelo PDV (testáveis sem banco)."""

import json
import re


def dividir_em_partes(total, partes, casas=2):
    """Divide ``total`` em ``partes`` valores que somam exatamente o total.

    Os centavos que sobram vão para as primeiras partes: R$ 100,00 / 3 = 33,34 + 33,33 + 33,33.
    """
    partes = max(int(partes or 1), 1)
    fator = 10 ** casas
    total_centavos = int(round(total * fator))
    base, resto = divmod(total_centavos, partes)
    return [(base + (1 if i < resto else 0)) / fator for i in range(partes)]


def so_digitos(texto):
    return re.sub(r"\D", "", texto or "")


def cpf_valido(cpf):
    cpf = so_digitos(cpf)
    if len(cpf) != 11 or cpf == cpf[0] * 11:
        return False
    for tamanho in (9, 10):
        soma = sum(int(cpf[i]) * (tamanho + 1 - i) for i in range(tamanho))
        digito = (soma * 10) % 11 % 10
        if digito != int(cpf[tamanho]):
            return False
    return True


def cnpj_valido(cnpj):
    cnpj = so_digitos(cnpj)
    if len(cnpj) != 14 or cnpj == cnpj[0] * 14:
        return False
    pesos1 = [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]
    pesos2 = [6] + pesos1
    for pesos, pos in ((pesos1, 12), (pesos2, 13)):
        soma = sum(int(cnpj[i]) * pesos[i] for i in range(len(pesos)))
        digito = 11 - soma % 11
        digito = 0 if digito >= 10 else digito
        if digito != int(cnpj[pos]):
            return False
    return True


def documento_valido(doc):
    d = so_digitos(doc)
    return cpf_valido(d) if len(d) == 11 else cnpj_valido(d) if len(d) == 14 else False


def ler_snapshot(texto):
    """Lê o last_order_preparation_change do PDV e devolve {uuid_da_linha: {qtd, nota, produto}}."""
    try:
        dados = json.loads(texto or "{}")
    except (TypeError, ValueError):
        return {}
    resultado = {}
    for chave, linha in (dados.get("lines") or {}).items():
        uuid = linha.get("uuid") or chave
        atual = resultado.setdefault(uuid, {"qtd": 0.0, "nota": linha.get("note") or "", "produto": linha.get("product_id"),
                                            "nome": linha.get("name") or linha.get("display_name") or "",
                                            "atributos": [a.get("name") for a in linha.get("attribute_value_ids") or [] if isinstance(a, dict)]})
        atual["qtd"] += float(linha.get("quantity") or 0.0)
        if linha.get("note"):
            atual["nota"] = linha["note"]
    return resultado
