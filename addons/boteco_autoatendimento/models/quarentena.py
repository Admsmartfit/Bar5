"""Motor de validação inteligente de pedidos do tablet/QR (N+X) — Etapa 14 do PRD Master.

Funções puras (sem ORM) para dar para testar cada regra isolada.

Cada item é um dicionário:
    {"produto_id", "nome", "tipo" (boteco_tipo_consumo), "serve" (rendimento),
     "max_rodada" (0 = automático), "qtd" (unidades neste envio), "valor" (R$ deste envio)}
"""

import math
import statistics

PRATOS = ("prato_individual", "prato_compartilhado")
COM_TRAVA_SKU = ("prato_individual", "prato_compartilhado", "sobremesa")
MINUTOS_SATURACAO = 45
AMOSTRA_MINIMA_ZSCORE = 20


def peso_prato(item):
    """Equivalente em pratos: individual vale 1; compartilhado vale o rendimento (R)."""
    if item["tipo"] == "prato_individual":
        return item["qtd"]
    if item["tipo"] == "prato_compartilhado":
        return item["qtd"] * max(item.get("serve") or 1, 1)
    return 0.0


def limite_rodada_pratos(n):
    """L = N + max(1, floor(N * 0,25))."""
    return n + max(1, math.floor(n * 0.25))


def limite_saturacao_45min(n):
    """ceil(N * 1,5) + 1."""
    return math.ceil(n * 1.5) + 1


def limite_bebida_giro(n):
    """max(4, 2N + 2)."""
    return max(4, n * 2 + 2)


def limite_garrafas(n):
    """ceil(N / 2)."""
    return math.ceil(n / 2)


def avaliar_regras_volume(itens, n, pratos_45min=0.0):
    """Regras 1 a 4. Devolve a lista de motivos (vazia = pedido normal)."""
    motivos = []
    n = max(int(n or 1), 1)

    # Regra 1: pratos principais na rodada
    e_prato = sum(peso_prato(i) for i in itens)
    limite = limite_rodada_pratos(n)
    if e_prato > limite:
        motivos.append("Pratos nesta rodada: %g para %d pessoa(s) (limite %d)" % (e_prato, n, limite))

    # Regra 2: saturação acumulada nos últimos 45 minutos
    limite_45 = limite_saturacao_45min(n)
    if e_prato and pratos_45min + e_prato > limite_45:
        motivos.append("Pratos em %d min: %g para %d pessoa(s) (limite %d)"
                       % (MINUTOS_SATURACAO, pratos_45min + e_prato, n, limite_45))

    # Regra 3: repetição acidental do mesmo item
    for item in itens:
        if item["tipo"] not in COM_TRAVA_SKU:
            continue
        maximo = min(n + 1, item["max_rodada"]) if item.get("max_rodada") else n + 1
        if (item["qtd"] >= 4 and n <= 3) or item["qtd"] > maximo:
            motivos.append("%g x %s para %d pessoa(s)" % (item["qtd"], item["nome"], n))

    # Regra 4: bebidas de giro e garrafas compartilhadas
    giro = sum(i["qtd"] for i in itens if i["tipo"] == "bebida_giro")
    if giro > limite_bebida_giro(n):
        motivos.append("Bebidas: %g para %d pessoa(s) (limite %d)" % (giro, n, limite_bebida_giro(n)))
    garrafas = sum(i["qtd"] for i in itens if i["tipo"] == "garrafa")
    if garrafas > limite_garrafas(n):
        motivos.append("Garrafas: %g para %d pessoa(s) (limite %d)" % (garrafas, n, limite_garrafas(n)))
    return motivos


def avaliar_ticket(valor_envio, n, tickets_por_pessoa):
    """Regra 5: anomalia financeira. ``tickets_por_pessoa``: histórico (R$/pessoa) dos últimos 90 dias.

    Retém se o envio passar de N x (mu + 2,5 sigma) ou de 3 x N x ticket médio.
    Com histórico pequeno (menos de 20 contas) a regra não age.
    """
    if len(tickets_por_pessoa) < AMOSTRA_MINIMA_ZSCORE or valor_envio <= 0:
        return None
    n = max(int(n or 1), 1)
    media = statistics.fmean(tickets_por_pessoa)
    desvio = statistics.pstdev(tickets_por_pessoa)
    limite = min(n * (media + 2.5 * desvio), 3 * n * media)
    if limite > 0 and valor_envio > limite:
        return "Valor do envio R$ %.2f para %d pessoa(s) (limite R$ %.2f)" % (valor_envio, n, limite)
    return None
