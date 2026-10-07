{
    "name": "Boteco – Cardápio",
    "summary": "Happy hour automático, oferta relâmpago, botão Acabou, +18, dados fiscais e cadastro rápido",
    "description": """
Etapa 1 do PRD: cadastros e cardápio.

* Setor de produção, tempo de preparo, descrição curta e foto quadrada (recorte automático).
* Marcação +18 nas bebidas alcoólicas.
* Happy hour por dias e horário (padrão: quarta a domingo, 17h às 21h) com troca de preço
  automática no tablet, no QR e no caixa, sem recarregar a tela.
* Oferta relâmpago com quantidade limite e botão "Lançar agora"; some sozinha ao esgotar.
* Botão "Acabou": tira o produto do tablet na hora, sem apagar.
* Dados fiscais do produto (NCM, CEST, CFOP, CST/CSOSN, origem) com aviso amarelo e relatório
  de pendências; valores padrão por categoria.
* QR Code de cada mesa em PDF para imprimir.
* Importar e exportar o cardápio por planilha.
""",
    "version": "18.0.1.0.0",
    "category": "Boteco",
    "author": "Boteco Raiz",
    "license": "LGPL-3",
    "depends": ["boteco_base", "pos_restaurant", "pos_self_order"],
    "data": [
        "security/ir.model.access.csv",
        "security/boteco_cardapio_security.xml",
        "data/boteco_happy_hour_data.xml",
        "data/ir_cron_data.xml",
        "views/product_template_views.xml",
        "views/product_category_views.xml",
        "views/boteco_happy_hour_views.xml",
        "views/boteco_oferta_relampago_views.xml",
        "wizard/boteco_cardapio_planilha_views.xml",
        "report/qr_mesas_report.xml",
        "views/menus.xml",
    ],
    "assets": {
        "point_of_sale._assets_pos": [
            "boteco_cardapio/static/src/app/**/*",
            "boteco_cardapio/static/src/pos/**/*",
        ],
        "pos_self_order.assets": [
            "boteco_cardapio/static/src/app/**/*",
            "boteco_cardapio/static/src/self_order/**/*",
        ],
    },
    "installable": True,
}
