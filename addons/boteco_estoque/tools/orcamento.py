"""Leitura de orçamentos de fornecedor: PDF (texto nativo) e texto colado.

O parser de texto procura, em cada linha, uma descrição seguida de um preço em reais:
    "Cebola nacional kg ....... R$ 3,99"  ->  ("Cebola nacional", 3.99, "kg")
"""

import io
import logging
import re

_logger = logging.getLogger(__name__)

UNIDADES = r"kg|g|un|und|unid|cx|caixa|lt|l|litro|pct|pacote|dz|duzia|fardo|bandeja|sc|saco"
PRECO = re.compile(
    r"(?:R\$\s*)?(?P<preco>\d{1,3}(?:\.\d{3})*,\d{2}|\d+,\d{2}|\d+\.\d{2})"
    r"(?:\s*(?:/|por|o|a)\s*(?P<un>" + UNIDADES + r")\b)?",
    re.IGNORECASE,
)
UNIDADE_SOLTA = re.compile(r"\b(?P<un>" + UNIDADES + r")\b\.?\s*$", re.IGNORECASE)
LIXO = re.compile(r"^[\s\-–—:.*•|]+|[\s\-–—:.*•|]+$")


def numero_br(texto):
    texto = texto.strip()
    if "," in texto:
        texto = texto.replace(".", "").replace(",", ".")
    return float(texto)


# Linhas que têm valor mas não são produto (condições do fornecedor)
NAO_E_ITEM = re.compile(
    r"\b(pedido m[ií]nimo|m[ií]nimo de|frete|entrega|total|subtotal|desconto|pagamento|pix|boleto|"
    r"cnpj|telefone|whats|hor[aá]rio|validade da tabela|v[aá]lido at[eé])\b", re.IGNORECASE)
# Enfeites de post (Instagram/encarte) que não fazem parte do nome do produto
ENFEITE = re.compile(r"#\w+|[^\w\s,./()%$-]|\b(oferta(s)? (do dia|de hoje)?|promo(ção|cao)|s[oó] hoje|imperd[ií]vel|"
                     r"aproveite|confira|apenas|somente)\b", re.IGNORECASE)
POR_N = re.compile(r"\b(\d{1,2})\s*(?:por|x)\s*$", re.IGNORECASE)  # "2 por 25,00" = 2 unidades por R$ 25
CONECTOR = re.compile(r"^(e|ou|,|;|\+|e também)\s+", re.IGNORECASE)


def ler_texto(texto):
    """Linhas de texto -> [{"descricao", "preco", "unidade"}]. Ignora linhas sem preço ou sem nome.

    Uma linha com vários preços (legenda de post: "Alcatra R$ 39,90/kg e Linguiça 2 por 25,00") vira vários itens.
    """
    itens = []
    for linha in (texto or "").splitlines():
        linha = linha.strip()
        if len(linha) < 4 or NAO_E_ITEM.search(linha):
            continue
        inicio = 0
        for achado in PRECO.finditer(linha):
            trecho = linha[inicio: achado.start()]
            inicio = achado.end()
            descricao = re.sub(r"\s+", " ", ENFEITE.sub(" ", trecho)).strip()
            descricao = CONECTOR.sub("", LIXO.sub("", descricao)).strip()
            unidade = (achado.group("un") or "").lower()
            solta = UNIDADE_SOLTA.search(descricao)
            if solta and not unidade:
                unidade = solta.group("un").lower()
                descricao = LIXO.sub("", descricao[: solta.start()]).strip()
            try:
                preco = numero_br(achado.group("preco"))
            except ValueError:
                continue
            por = POR_N.search(descricao)
            if por:  # "2 por 25,00": preço de cada um
                preco = preco / int(por.group(1))
                descricao = descricao[: por.start()].strip()
            descricao = LIXO.sub("", descricao).strip()
            if len(descricao) < 3 or not re.search(r"[A-Za-zÀ-ú]", descricao) or preco <= 0:
                continue
            itens.append({"descricao": descricao, "preco": round(preco, 4), "unidade": unidade})
    return itens


def texto_do_pdf(conteudo):
    """Texto de um PDF com texto nativo (PDF escaneado precisa ir como foto)."""
    from odoo.tools.pdf import PdfReader  # PyPDF2/pypdf, o que estiver instalado

    leitor = PdfReader(io.BytesIO(conteudo))
    partes = []
    for pagina in leitor.pages:
        extrair = getattr(pagina, "extract_text", None) or getattr(pagina, "extractText")
        partes.append(extrair() or "")
    return "\n".join(partes)



