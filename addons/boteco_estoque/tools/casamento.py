"""Reconhecer o insumo de uma cotação ("Cerveja Brahma 600ml cx c/24 R$ 189,90") com segurança.

Regras (auditoria de 19/11/2026: o casamento antigo ligava "Cebola" a "Calabresa acebolada"):
* compara PALAVRAS INTEIRAS, sem acento e sem plural ("cebola" não casa com "acebolada");
* todas as palavras do nome do insumo precisam aparecer na descrição do fornecedor;
* TAMANHO tem que bater (330 ml não é 600 ml; 2 L não é lata);
* EMBALAGEM vira preço por unidade do insumo (cx c/24 -> /24; pacote 2,5 kg -> /2,5; "2 por 25,00" -> 12,50).
"""

import re
import unicodedata

PARADAS = {
    "de", "da", "do", "das", "dos", "com", "sem", "e", "a", "o", "em", "para", "por", "c", "s", "tipo", "unidade",
    "un", "und", "unid", "cx", "caixa", "pct", "pacote", "fardo", "kg", "g", "gr", "l", "lt", "litro", "litros",
    "ml", "dz", "duzia", "bandeja", "sc", "saco", "peca", "oferta", "promocao", "hoje", "so", "r", "preco",
    "serve", "porcao", "kilo", "quilo", "garrafa", "pet",
}
# Tamanhos implícitos no nome (o fornecedor escreve "2L", o insumo chama "lata")
TAMANHO_PALAVRA = {"lata": ("ml", 350.0), "latao": ("ml", 473.0), "long neck": ("ml", 340.0), "litrao": ("ml", 1000.0)}
MEDIDA = re.compile(r"(\d+(?:[.,]\d+)?)\s*(ml|l|lt|litros?|g|gr|grs|kg|kilos?|quilos?)\b", re.I)
EMBALAGEM = re.compile(
    r"(?:\bc\s*/\s*|\bcom\s+|\bx\s*|\bcx\s*(?:c\s*/\s*)?|\bfardo\s*(?:c\s*/\s*)?|\bpack\s*)(\d{1,3})\b(?!\s*(?:ml|l|lt|g|kg))"
    r"|\b(\d{1,3})\s*(?:un|und|unid|unidades)\b",
    re.I,
)


def sem_acento(texto):
    return unicodedata.normalize("NFKD", texto or "").encode("ascii", "ignore").decode().lower()


def palavras(texto):
    """Palavras significativas (sem acento, sem plural simples, sem números/medidas)."""
    resultado = set()
    for p in re.findall(r"[a-z]+", MEDIDA.sub(" ", sem_acento(texto))):
        if len(p) < 3 or p in PARADAS:
            continue
        if len(p) > 4 and p.endswith("s"):
            p = p[:-1]
        resultado.add(p)
    return resultado


def medida(texto):
    """('ml', 600.0) / ('g', 2500.0) ou None: o tamanho escrito (ou implícito: lata, long neck)."""
    normal = sem_acento(texto)
    achou = MEDIDA.search(normal)
    if achou:
        valor = float(achou.group(1).replace(",", "."))
        un = achou.group(2).lower()
        if un in ("l", "lt", "litro", "litros"):
            return ("ml", valor * 1000)
        if un == "ml":
            return ("ml", valor)
        if un in ("kg", "kilo", "kilos", "quilo", "quilos"):
            return ("g", valor * 1000)
        return ("g", valor)
    for palavra, tamanho in TAMANHO_PALAVRA.items():
        if re.search(r"\b%s\b" % palavra, normal):
            return tamanho
    return None


def tamanhos_compativeis(a, b):
    if not a or not b or a[0] != b[0]:
        return True  # sem tamanho de um dos lados (ou kg x ml): não dá para dizer que é diferente
    return abs(a[1] - b[1]) <= 0.12 * max(a[1], b[1])


def embalagem(texto):
    """Quantas unidades vêm na embalagem cotada (cx c/24 -> 24). 1 se não disser."""
    achou = EMBALAGEM.search(sem_acento(texto))
    if not achou:
        return 1
    n = int(achou.group(1) or achou.group(2))
    return n if 1 < n <= 500 else 1


def pontuar(descricao, nome_insumo):
    """0..1: fração das palavras do insumo presentes na descrição; 0 se o tamanho não bate."""
    alvo = palavras(nome_insumo)
    if not alvo:
        return 0.0
    if not tamanhos_compativeis(medida(descricao), medida(nome_insumo)):
        return 0.0
    return len(alvo & palavras(descricao)) / len(alvo)


def quantidade_no_insumo(descricao, unidade_cotada, uom_insumo):
    """Quantas unidades do insumo o preço cotado compra (o preço por unidade = preço / quantidade).

    uom_insumo: 'unit' (unidade), 'weight' (kg/g) ou 'volume' (L/ml), com o fator para kg ou L.
    Devolve (quantidade, certeza: bool).
    """
    categoria, por_unidade_base = uom_insumo  # ex.: ("weight", 1.0) para kg; ("weight", 0.001) para g
    un = (unidade_cotada or "").lower()
    tam = medida(descricao)
    if categoria == "unit":
        return float(embalagem(descricao)), True
    if categoria == "weight":
        if un in ("kg",) and not tam:
            return 1.0 / por_unidade_base if por_unidade_base else 1.0, True
        if tam and tam[0] == "g":
            kg = tam[1] / 1000.0 * embalagem(descricao)
            return kg / por_unidade_base, True
        return 1.0, un == "kg"
    if categoria == "volume":
        if tam and tam[0] == "ml":
            litros = tam[1] / 1000.0 * embalagem(descricao)
            return litros / por_unidade_base, True
        return 1.0, un in ("l", "lt", "litro")
    return 1.0, False
