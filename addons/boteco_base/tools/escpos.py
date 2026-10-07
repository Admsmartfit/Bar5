"""Montagem e envio de tickets ESC/POS para impressoras térmicas de rede (80 mm).

Funciona com Epson TM (ePOS ou não), Elgin, Bematech, Daruma e genéricas que aceitam
ESC/POS bruto na porta 9100. Sem dependências externas.

Exemplo::

    t = Ticket(colunas=48)
    t.titulo("MESA 12")
    t.texto("2x Chope 300 ml", tamanho=2)
    t.corte()
    enviar(t.bytes(), "192.168.10.50", 9100)
"""

import socket
import unicodedata

ESC = b"\x1b"
GS = b"\x1d"

# Tabelas de caracteres ESC t n (Epson). 3 = PC860 (português).
CODEPAGES = {
    "cp860": 3,
    "cp850": 2,
    "cp437": 0,
}


class ImpressoraIndisponivel(Exception):
    """A impressora não respondeu (desligada, sem papel, fora da rede)."""


class Ticket:
    def __init__(self, colunas=48, codepage="cp860"):
        self.colunas = colunas
        self.codepage = codepage if codepage in CODEPAGES else "cp860"
        self._buf = bytearray()
        self._buf += ESC + b"@"  # reset
        self._buf += ESC + b"t" + bytes([CODEPAGES[self.codepage]])

    # ------------------------------------------------------------------ texto
    def _enc(self, texto):
        texto = str(texto or "")
        try:
            return texto.encode(self.codepage)
        except UnicodeEncodeError:
            # Remove o que a impressora não sabe desenhar (emoji etc.) sem perder acentos
            limpo = []
            for ch in texto:
                try:
                    ch.encode(self.codepage)
                    limpo.append(ch)
                except UnicodeEncodeError:
                    base = unicodedata.normalize("NFKD", ch).encode("ascii", "ignore").decode()
                    limpo.append(base or "?")
            return "".join(limpo).encode(self.codepage, errors="replace")

    def alinhar(self, modo="esquerda"):
        n = {"esquerda": 0, "centro": 1, "direita": 2}.get(modo, 0)
        self._buf += ESC + b"a" + bytes([n])
        return self

    def negrito(self, ligado=True):
        self._buf += ESC + b"E" + (b"\x01" if ligado else b"\x00")
        return self

    def inverso(self, ligado=True):
        self._buf += GS + b"B" + (b"\x01" if ligado else b"\x00")
        return self

    def tamanho(self, n=1):
        """1 = normal, 2 = dobro, 3 = triplo (largura e altura)."""
        n = max(1, min(int(n), 8)) - 1
        self._buf += GS + b"!" + bytes([(n << 4) | n])
        return self

    def colunas_no_tamanho(self, tamanho):
        return max(8, self.colunas // max(1, tamanho))

    def texto(self, texto, tamanho=1, negrito=False, alinhar="esquerda", inverso=False):
        self.alinhar(alinhar).tamanho(tamanho).negrito(negrito)
        if inverso:
            self.inverso(True)
        for linha in str(texto or "").split("\n"):
            for parte in self._quebrar(linha, self.colunas_no_tamanho(tamanho)):
                self._buf += self._enc(parte) + b"\n"
        if inverso:
            self.inverso(False)
        self.tamanho(1).negrito(False).alinhar("esquerda")
        return self

    def titulo(self, texto):
        return self.texto(texto, tamanho=2, negrito=True, alinhar="centro")

    def destaque(self, texto):
        """Faixa invertida (fundo preto) para observações que não podem passar batido."""
        return self.texto(texto, tamanho=2, negrito=True, inverso=True)

    def colunas_texto(self, esquerda, direita, tamanho=1, negrito=False):
        largura = self.colunas_no_tamanho(tamanho)
        direita = str(direita or "")
        esquerda = str(esquerda or "")[: max(1, largura - len(direita) - 1)]
        espacos = max(1, largura - len(esquerda) - len(direita))
        return self.texto(esquerda + " " * espacos + direita, tamanho=tamanho, negrito=negrito)

    def separador(self, char="-"):
        self._buf += self._enc(char * self.colunas) + b"\n"
        return self

    def avancar(self, linhas=1):
        self._buf += ESC + b"d" + bytes([max(0, min(linhas, 255))])
        return self

    def bip(self, vezes=2):
        # ESC B n t (Epson compatível); impressoras sem buzzer ignoram
        self._buf += ESC + b"B" + bytes([max(1, min(vezes, 9)), 2])
        return self

    def qrcode(self, dados, modulo=6):
        dados = str(dados).encode("utf-8")
        tam = len(dados) + 3
        pl, ph = tam % 256, tam // 256
        self.alinhar("centro")
        self._buf += GS + b"(k\x04\x001A2\x00"                    # modelo 2
        self._buf += GS + b"(k\x03\x001C" + bytes([modulo])        # tamanho do módulo
        self._buf += GS + b"(k\x03\x001E1"                         # correção M
        self._buf += GS + b"(k" + bytes([pl, ph]) + b"1P0" + dados  # armazena
        self._buf += GS + b"(k\x03\x001Q0"                         # imprime
        self._buf += b"\n"
        return self.alinhar("esquerda")

    def corte(self):
        self.avancar(4)
        self._buf += GS + b"V\x42\x00"  # corte parcial com avanço
        return self

    def bytes(self):
        return bytes(self._buf)

    @staticmethod
    def _quebrar(linha, largura):
        if len(linha) <= largura:
            return [linha]
        partes, atual = [], ""
        for palavra in linha.split(" "):
            while len(palavra) > largura:
                if atual:
                    partes.append(atual)
                    atual = ""
                partes.append(palavra[:largura])
                palavra = palavra[largura:]
            candidato = (atual + " " + palavra).strip() if atual else palavra
            if len(candidato) <= largura:
                atual = candidato
            else:
                partes.append(atual)
                atual = palavra
        if atual:
            partes.append(atual)
        return partes


def enviar(dados, host, porta=9100, timeout=3.0):
    """Envia bytes brutos para a impressora. Levanta ImpressoraIndisponivel se falhar."""
    try:
        with socket.create_connection((host, int(porta)), timeout=timeout) as sock:
            sock.settimeout(timeout)
            sock.sendall(dados)
    except OSError as erro:
        raise ImpressoraIndisponivel(str(erro)) from erro


def testar_conexao(host, porta=9100, timeout=1.0):
    """True se a porta da impressora aceita conexão."""
    try:
        with socket.create_connection((host, int(porta)), timeout=timeout):
            return True
    except OSError:
        return False
