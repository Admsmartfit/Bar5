"""Funções de rede: conferir se um IP pertence às faixas da rede do bar."""

import ipaddress


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
