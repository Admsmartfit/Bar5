"""Leitura de orçamentos de fornecedor: PDF (texto nativo), texto colado e foto (API de visão).

O parser de texto procura, em cada linha, uma descrição seguida de um preço em reais:
    "Cebola nacional kg ....... R$ 3,99"  ->  ("Cebola nacional", 3.99, "kg")
"""

import base64
import io
import json
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


def ler_texto(texto):
    """Linhas de texto -> [{"descricao", "preco", "unidade"}]. Ignora linhas sem preço ou sem nome."""
    itens = []
    for linha in (texto or "").splitlines():
        linha = linha.strip()
        if len(linha) < 4:
            continue
        precos = list(PRECO.finditer(linha))
        if not precos:
            continue
        achado = precos[-1]  # o preço costuma ser o último número da linha
        descricao = LIXO.sub("", re.sub(r"\s+", " ", linha[: achado.start()])).strip()
        unidade = (achado.group("un") or "").lower()
        solta = UNIDADE_SOLTA.search(descricao)
        if solta and not unidade:
            unidade = solta.group("un").lower()
            descricao = LIXO.sub("", descricao[: solta.start()]).strip()
        if len(descricao) < 3 or not re.search(r"[A-Za-zÀ-ú]", descricao):
            continue
        try:
            preco = numero_br(achado.group("preco"))
        except ValueError:
            continue
        if preco <= 0:
            continue
        itens.append({"descricao": descricao, "preco": preco, "unidade": unidade})
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


PROMPT_VISAO = (
    "Esta imagem é um orçamento, tabela de preços ou encarte de um fornecedor de restaurante no Brasil. "
    "Liste todos os produtos com preço. Responda só com JSON: "
    '{"itens": [{"descricao": "texto do produto", "preco": 12.34, "unidade": "kg|un|cx|..."}]}. '
    "Use ponto como separador decimal. Não invente itens."
)


def ler_imagem_gemini(conteudo, mimetype, chave, modelo="gemini-2.5-flash", timeout=60):
    """Foto -> itens, pela API do Gemini (saída JSON). Precisa da chave configurada pelo dono."""
    import requests

    url = "https://generativelanguage.googleapis.com/v1beta/models/%s:generateContent" % modelo
    corpo = {
        "contents": [{"parts": [
            {"text": PROMPT_VISAO},
            {"inline_data": {"mime_type": mimetype or "image/jpeg", "data": base64.b64encode(conteudo).decode()}},
        ]}],
        "generationConfig": {"responseMimeType": "application/json", "temperature": 0},
    }
    resposta = requests.post(url, json=corpo, headers={"x-goog-api-key": chave}, timeout=timeout)
    resposta.raise_for_status()
    texto = resposta.json()["candidates"][0]["content"]["parts"][0]["text"]
    return normalizar_json(texto)


def normalizar_json(texto):
    try:
        dados = json.loads(texto)
    except ValueError:
        _logger.warning("Resposta da leitura de imagem não é JSON: %s", texto[:200])
        return []
    itens = []
    for item in dados.get("itens", []) if isinstance(dados, dict) else []:
        try:
            preco = float(str(item.get("preco")).replace(",", "."))
        except (TypeError, ValueError):
            continue
        descricao = str(item.get("descricao") or "").strip()
        if descricao and preco > 0:
            itens.append({"descricao": descricao, "preco": preco, "unidade": str(item.get("unidade") or "").lower()})
    return itens
