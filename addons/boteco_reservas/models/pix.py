"""Pix "copia e cola" estático (BR Code / EMV-MPM do Banco Central), sem depender de banco ou PSP."""

import re
import unicodedata


def _campo(identificador, valor):
    return "%s%02d%s" % (identificador, len(valor), valor)


def _limpo(texto, tamanho):
    texto = unicodedata.normalize("NFKD", texto or "").encode("ascii", "ignore").decode()
    return re.sub(r"[^A-Za-z0-9 ]", "", texto).upper().strip()[:tamanho] or "BAR"


def crc16(dados):
    """CRC16-CCITT (polinômio 0x1021, início 0xFFFF), como pede o manual do BR Code."""
    crc = 0xFFFF
    for byte in dados.encode():
        crc ^= byte << 8
        for _ in range(8):
            crc = ((crc << 1) ^ 0x1021) if crc & 0x8000 else (crc << 1)
            crc &= 0xFFFF
    return "%04X" % crc


def payload_pix(chave, nome, cidade, valor, identificador):
    conta = _campo("00", "br.gov.bcb.pix") + _campo("01", chave.strip())
    txid = re.sub(r"[^A-Za-z0-9]", "", identificador or "")[:25] or "***"
    corpo = (
        _campo("00", "01")
        + _campo("26", conta)
        + _campo("52", "0000")
        + _campo("53", "986")
        + _campo("54", "%.2f" % valor)
        + _campo("58", "BR")
        + _campo("59", _limpo(nome, 25))
        + _campo("60", _limpo(cidade, 15))
        + _campo("62", _campo("05", txid))
        + "6304"
    )
    return corpo + crc16(corpo)
