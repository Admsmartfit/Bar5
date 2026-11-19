{
    "name": "Boteco – Cozinha central",
    "summary": "Produção em lotes rastreáveis: tela com 3 botões, etiqueta do saco a vácuo, FEFO, "
    "bloqueio de vencido, temperaturas e rastreio do lote",
    "description": """
Etapa 6 do PRD: produzir em lotes rastreáveis, etiquetar e abastecer o bar e os clientes B2B.

Nativo (configurado): Fabricação (receitas, ordens de produção, consumo de insumos), lotes com
validade, saída pelo lote que vence primeiro (FEFO) e rastreabilidade.

Programado aqui:
* Receitas com rendimento, perda esperada, validade (congelado/resfriado), conservação e modo de preparo.
* Plano de produção sugerido (estoque, pedidos B2B em aberto e média de saída por dia da semana).
* Tela de produção em tablet: "Iniciar", "Pesar" (único dado digitado) e "Finalizar".
* Ao finalizar: lote com código, fabricação e validade; baixa dos insumos; rendimento real x esperado;
  etiqueta ZPL do saco a vácuo impressa na hora (produto, fabricação, validade, lote, peso,
  conservação, empresa, CNPJ, registro sanitário e QR do lote).
* Transferência para o bar lendo o QR da etiqueta; confirmação de recebimento no bar.
* Lotes vencendo em 3 dias em amarelo; lote vencido bloqueado em qualquer movimentação.
* Registro diário de temperatura de freezers e câmaras (planilha da Vigilância em PDF).
* Rastreio do lote: de quais insumos veio e para quem foi (bar e clientes B2B).
""",
    "version": "18.0.1.0.0",
    "category": "Boteco",
    "author": "Boteco Raiz",
    "license": "LGPL-3",
    "depends": ["boteco_kds", "boteco_estoque", "mrp", "product_expiry", "sale_stock"],
    "data": [
        "security/ir.model.access.csv",
        "data/ir_sequence_data.xml",
        "views/product_template_views.xml",
        "views/mrp_views.xml",
        "views/stock_lot_views.xml",
        "views/boteco_temperatura_views.xml",
        "views/boteco_plano_producao_views.xml",
        "views/boteco_rastreio_views.xml",
        "views/stock_warehouse_views.xml",
        "views/separacao_templates.xml",
        "report/temperatura_report.xml",
        "views/menus.xml",
        "data/menus_recursos_data.xml",
        "data/boteco_ajuda_artigos.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "boteco_cozinha_central/static/src/producao/**/*",
        ],
        "boteco_cozinha_central.assets_separacao": [
            "boteco_base/static/src/css/boteco_tokens.css",
            "boteco_cozinha_central/static/src/separacao/separacao.css",
            "boteco_cozinha_central/static/src/separacao/separacao.js",
        ],
    },
    "installable": True,
}
