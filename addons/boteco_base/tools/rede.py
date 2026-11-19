"""Funções de rede: conferir se um IP pertence às faixas da rede do bar."""

import ipaddress


def normalizar_redes(texto):
    """'192.168.15.1' (endereço do roteador) -> '192.168.15.0/24' (a rede inteira). Erro se não for rede.

    Quem configura costuma copiar o endereço do roteador; gravar só esse endereço deixaria
    todos os outros celulares de fora.
    """
    resultado = []
    for parte in (texto or "").replace(";", ",").split(","):
        parte = parte.strip()
        if not parte:
            continue
        if "/" not in parte:
            parte += "/24"
        rede = ipaddress.ip_network(parte, strict=False)  # ValueError se não for rede
        if str(rede) not in resultado:
            resultado.append(str(rede))
    return ", ".join(resultado)


def faixas(texto):
    """Converte '192.168.10.0/24, 10.0.0.5' em lista de redes; ignora entradas inválidas."""
    redes = []
    for parte in (texto or "").replace(";", ",").split(","):
        parte = parte.strip()
        if not parte:
            continue
        try:
            redes.append(ipaddress.ip_network(parte, strict=False))
        except ValueError:
            continue
    return redes


def ip_na_rede(ip, texto_faixas, vazio_libera=True):
    """True se o IP está em alguma faixa. Sem faixas configuradas, libera (vazio_libera)."""
    redes = faixas(texto_faixas)
    if not redes:
        return vazio_libera
    try:
        endereco = ipaddress.ip_address((ip or "").strip())
    except ValueError:
        return False
    return any(endereco in rede for rede in redes)
