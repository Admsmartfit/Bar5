"""Coletor de ofertas dos fornecedores (Etapa 35) — roda FORA do servidor do PDV, em contêiner próprio.

* Busca no Odoo o que ler e quando: GET /boteco/compras/api/fontes (token próprio).
* Instagram 1 vez por dia (padrão 8:00); sites 2 vezes por semana (padrão seg e qui, 8:00).
* Sites com JavaScript via Playwright; Instagram via instaloader (perfis públicos).
* Manda o texto das ofertas (só as linhas com preço e com as palavras-chave do fornecedor) para
  POST /boteco/compras/api/cotacoes. O Odoo lê os itens com o mesmo leitor dos orçamentos.

Variáveis: BOTECO_URL (ex.: http://odoo:8069), BOTECO_COLETOR_TOKEN, TZ (America/Sao_Paulo).
"""

import logging
import os
import re
import sys
import time
from datetime import datetime, timedelta

import requests

VERSAO = "1.0"
URL = os.environ.get("BOTECO_URL", "http://odoo:8069").rstrip("/")
TOKEN = os.environ.get("BOTECO_COLETOR_TOKEN", "")
TEMPO_POR_FONTE = 60  # segundos: site lento não segura os outros
PRECO = re.compile(r"(R\$\s*)?\d{1,4}(?:[.,]\d{3})*[.,]\d{2}")
ESTADO = "/dados/ultimas_execucoes.txt"

logging.basicConfig(level=logging.INFO, format="%(asctime)s coletor %(levelname)s %(message)s")
log = logging.getLogger("coletor")


def odoo(metodo, caminho, **kwargs):
    resposta = requests.request(metodo, URL + caminho, headers={"Authorization": "Bearer " + TOKEN}, timeout=30, **kwargs)
    resposta.raise_for_status()
    return resposta.json()


def linhas_de_oferta(texto, palavras):
    """Só as linhas com preço (e com alguma palavra-chave, se o fornecedor cadastrou)."""
    palavras = [p.lower() for p in palavras or []]
    escolhidas = []
    for linha in (texto or "").splitlines():
        linha = linha.strip()
        if not linha or not PRECO.search(linha):
            continue
        if palavras and not any(p in linha.lower() for p in palavras):
            continue
        escolhidas.append(linha)
    return "\n".join(escolhidas)


def ler_site(url):
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        navegador = p.chromium.launch(args=["--no-sandbox"])
        try:
            pagina = navegador.new_page()
            pagina.goto(url, timeout=TEMPO_POR_FONTE * 1000, wait_until="networkidle")
            return pagina.inner_text("body")
        finally:
            navegador.close()


def ler_instagram(perfil, desde):
    import instaloader

    carregador = instaloader.Instaloader(download_pictures=False, download_videos=False, save_metadata=False, quiet=True)
    posts = []
    for post in instaloader.Profile.from_username(carregador.context, perfil).get_posts():
        if post.date_utc < desde or len(posts) >= 6:
            break
        posts.append((post.caption or "", "https://www.instagram.com/p/%s/" % post.shortcode))
    return posts


def ultimas():
    try:
        with open(ESTADO, encoding="utf-8") as arquivo:
            return dict(l.strip().split("=", 1) for l in arquivo if "=" in l)
    except FileNotFoundError:
        return {}


def gravar(chave, valor):
    dados = ultimas()
    dados[chave] = valor
    os.makedirs(os.path.dirname(ESTADO), exist_ok=True)
    with open(ESTADO, "w", encoding="utf-8") as arquivo:
        arquivo.writelines("%s=%s\n" % kv for kv in dados.items())


def hora_passou(hhmm, agora):
    h, m = (int(x) for x in hhmm.split(":"))
    return (agora.hour, agora.minute) >= (h, m)


def rodar(tipo, fontes):
    cotacoes = []
    for fonte in fontes:
        try:
            if tipo == "sites" and fonte.get("site"):
                texto = linhas_de_oferta(ler_site(fonte["site"]), fonte.get("palavras"))
                if texto:
                    cotacoes.append({"fornecedor_id": fonte["fornecedor_id"], "fonte": "site", "link": fonte["site"],
                                     "texto": texto})
            elif tipo == "instagram" and fonte.get("instagram"):
                for legenda, link in ler_instagram(fonte["instagram"], datetime.utcnow() - timedelta(days=2)):
                    texto = linhas_de_oferta(legenda, fonte.get("palavras"))
                    if texto:
                        cotacoes.append({"fornecedor_id": fonte["fornecedor_id"], "fonte": "instagram", "link": link,
                                         "texto": texto})
        except Exception:  # noqa: BLE001 — um fornecedor com problema não para os outros
            log.warning("Fonte %s (%s) falhou", fonte.get("nome"), tipo, exc_info=True)
    resposta = odoo("POST", "/boteco/compras/api/cotacoes", json={"coletor_versao": VERSAO, "cotacoes": cotacoes})
    log.info("%s: %s bloco(s) enviados, %s item(ns) recebidos", tipo, len(cotacoes), resposta.get("itens"))


def ciclo():
    agenda = odoo("GET", "/boteco/compras/api/fontes")
    if agenda.get("desligado"):
        return
    agora = datetime.now()
    hoje = agora.strftime("%Y-%m-%d")
    feitas = ultimas()
    if feitas.get("instagram") != hoje and hora_passou(agenda.get("instagram_hora", "08:00"), agora):
        rodar("instagram", agenda["fontes"])
        gravar("instagram", hoje)
    dias = [d.strip() for d in str(agenda.get("sites_dias", "0,3")).split(",")]
    if (str(agora.weekday()) in dias and feitas.get("sites") != hoje
            and hora_passou(agenda.get("sites_hora", "08:00"), agora)):
        rodar("sites", agenda["fontes"])
        gravar("sites", hoje)
    # Sinal de vida (o Odoo deixa de ler o Instagram por conta própria enquanto o coletor responde)
    odoo("POST", "/boteco/compras/api/cotacoes", json={"coletor_versao": VERSAO, "cotacoes": []})


def main():
    if not TOKEN:
        log.error("Defina BOTECO_COLETOR_TOKEN (Odoo › Compras › WhatsApp e coletor).")
        sys.exit(1)
    while True:
        try:
            ciclo()
        except Exception:  # noqa: BLE001
            log.warning("Ciclo falhou; tento de novo em 10 minutos", exc_info=True)
        time.sleep(600)


if __name__ == "__main__":
    main()
