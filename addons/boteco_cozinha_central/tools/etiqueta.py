"""Etiqueta do saco a vácuo (100 x 70 mm) em ZPL (Zebra, Elgin, Argox no modo ZPL) ou TSPL.

Campos exigidos pela Vigilância: produto, data de fabricação, validade, lote, peso líquido,
conservação, fabricante (razão social e CNPJ) e, quando houver, número do registro sanitário.
"""

import unicodedata


def _limpo(texto, tamanho=None):
    """ZPL com ^CI28 aceita UTF-8; só tira caracteres de controle e o ^ e ~ (comandos ZPL)."""
    texto = "".join(c for c in str(texto or "") if unicodedata.category(c)[0] != "C")
    texto = texto.replace("^", " ").replace("~", " ")
    return texto[:tamanho] if tamanho else texto


def zpl(dados):
    """dados: produto, fabricacao, validade, lote, peso, conservacao, empresa, cnpj, registro, qr."""
    linhas = [
        "^XA",
        "^CI28",            # UTF-8 (acentos)
        "^PW800^LL560",     # 100 x 70 mm a 203 dpi
        "^FO30,25^A0N,52,52^FB740,2,0,L^FD%s^FS" % _limpo(dados["produto"], 60),
        "^FO30,140^A0N,30,30^FDFabricação: %s^FS" % _limpo(dados["fabricacao"]),
        "^FO30,180^A0N,40,40^FDVALIDADE: %s^FS" % _limpo(dados["validade"]),
        "^FO30,235^A0N,30,30^FDLote: %s^FS" % _limpo(dados["lote"]),
        "^FO30,275^A0N,30,30^FDPeso líquido: %s^FS" % _limpo(dados["peso"]),
        "^FO30,315^GB500,60,3^FS",
        "^FO45,330^A0N,30,30^FD%s^FS" % _limpo(dados["conservacao"], 40),
        "^FO30,395^A0N,24,24^FD%s^FS" % _limpo(dados["empresa"], 45),
        "^FO30,425^A0N,24,24^FDCNPJ: %s^FS" % _limpo(dados["cnpj"]),
    ]
    if dados.get("registro"):
        linhas.append("^FO30,455^A0N,24,24^FDRegistro: %s^FS" % _limpo(dados["registro"]))
    linhas += [
        "^FO560,300^BQN,2,6^FDQA,%s^FS" % _limpo(dados["qr"]),
        "^PQ%d" % max(int(dados.get("copias") or 1), 1),
        "^XZ",
    ]
    return "\n".join(linhas).encode("utf-8")


def tspl(dados):
    linhas = [
        "SIZE 100 mm,70 mm", "GAP 2 mm,0", "CODEPAGE UTF-8", "CLS",
        'TEXT 30,25,"4",0,1,1,"%s"' % _limpo(dados["produto"], 32),
        'TEXT 30,140,"3",0,1,1,"Fabricacao: %s"' % _limpo(dados["fabricacao"]),
        'TEXT 30,180,"4",0,1,1,"VALIDADE: %s"' % _limpo(dados["validade"]),
        'TEXT 30,235,"3",0,1,1,"Lote: %s"' % _limpo(dados["lote"]),
        'TEXT 30,275,"3",0,1,1,"Peso: %s"' % _limpo(dados["peso"]),
        'TEXT 30,330,"3",0,1,1,"%s"' % _limpo(dados["conservacao"], 40),
        'TEXT 30,395,"2",0,1,1,"%s"' % _limpo(dados["empresa"], 45),
        'TEXT 30,425,"2",0,1,1,"CNPJ: %s"' % _limpo(dados["cnpj"]),
        'QRCODE 560,300,M,6,A,0,"%s"' % _limpo(dados["qr"]),
        "PRINT %d" % max(int(dados.get("copias") or 1), 1),
    ]
    return ("\r\n".join(linhas) + "\r\n").encode("utf-8")
