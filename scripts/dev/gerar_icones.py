"""Gera os ícones (static/description/icon.png) dos módulos boteco_*. Rodar dentro da imagem odoo:18."""
import os
import sys
from PIL import Image, ImageDraw, ImageFont

ICONES = {
    "boteco_base": ("#f59e0b", "B"),
    "boteco_cardapio": ("#16a34a", "C"),
    "boteco_pos": ("#2563eb", "$"),
    "boteco_kds": ("#ea580c", "K"),
    "boteco_autoatendimento": ("#7c3aed", "Q"),
    "boteco_estoque": ("#0891b2", "E"),
    "boteco_cozinha_central": ("#be123c", "CC"),
    "boteco_b2b": ("#0d9488", "B2"),
    "boteco_painel": ("#111827", "P"),
    "boteco_fiscal_export": ("#4b5563", "NF"),
    "boteco_treinamento": ("#dc2626", "T"),
}

raiz = sys.argv[1]
for modulo, (cor, letra) in ICONES.items():
    pasta = os.path.join(raiz, modulo, "static", "description")
    if not os.path.isdir(os.path.join(raiz, modulo)):
        continue
    os.makedirs(pasta, exist_ok=True)
    img = Image.new("RGBA", (256, 256), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle((0, 0, 255, 255), radius=48, fill=cor)
    try:
        fonte = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 120 if len(letra) == 1 else 96)
    except OSError:
        fonte = ImageFont.load_default()
    caixa = d.textbbox((0, 0), letra, font=fonte)
    w, h = caixa[2] - caixa[0], caixa[3] - caixa[1]
    d.text(((256 - w) / 2 - caixa[0], (256 - h) / 2 - caixa[1]), letra, fill="white", font=fonte)
    img.save(os.path.join(pasta, "icon.png"))
    print("ícone", modulo)
