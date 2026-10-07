"""Validação dos dados fiscais do produto (para a emissão posterior da nota)."""

import re

ORIGENS = [
    ("0", "0 – Nacional"),
    ("1", "1 – Estrangeira, importação direta"),
    ("2", "2 – Estrangeira, adquirida no mercado interno"),
    ("3", "3 – Nacional, conteúdo de importação > 40% e ≤ 70%"),
    ("4", "4 – Nacional, processos produtivos básicos"),
    ("5", "5 – Nacional, conteúdo de importação ≤ 40%"),
    ("6", "6 – Estrangeira, importação direta sem similar (CAMEX)"),
    ("7", "7 – Estrangeira, mercado interno sem similar (CAMEX)"),
    ("8", "8 – Nacional, conteúdo de importação > 70%"),
]

UNIDADES = [
    ("UN", "UN – unidade"),
    ("KG", "KG – quilo"),
    ("G", "G – grama"),
    ("L", "L – litro"),
    ("ML", "ML – mililitro"),
    ("PC", "PC – porção"),
    ("DZ", "DZ – dúzia"),
    ("CX", "CX – caixa"),
]


def so_digitos(valor):
    return re.sub(r"\D", "", valor or "")


def formatar_ncm(valor):
    d = so_digitos(valor)
    if len(d) == 8:
        return "%s.%s.%s" % (d[:4], d[4:6], d[6:])
    return valor


def pendencias_fiscais(ncm, cfop, cst_csosn, origem, cest=None):
    """Lista de textos do que falta/está errado. Vazia = tudo certo."""
    erros = []
    ncm_d = so_digitos(ncm)
    if not ncm_d:
        erros.append("sem NCM")
    elif len(ncm_d) != 8:
        erros.append("NCM precisa ter 8 números")
    cfop_d = so_digitos(cfop)
    if not cfop_d:
        erros.append("sem CFOP")
    elif len(cfop_d) != 4 or cfop_d[0] not in "1234567":
        erros.append("CFOP inválido")
    cst_d = so_digitos(cst_csosn)
    if not cst_d:
        erros.append("sem CST/CSOSN")
    elif len(cst_d) not in (2, 3):
        erros.append("CST/CSOSN precisa ter 2 ou 3 números")
    if origem in (None, False, ""):
        erros.append("sem origem")
    cest_d = so_digitos(cest)
    if cest_d and len(cest_d) != 7:
        erros.append("CEST precisa ter 7 números")
    return erros
