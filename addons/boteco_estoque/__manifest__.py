{
    "name": "Boteco – Estoque e compras do bar",
    "summary": "CMV por noite, leitor do XML da NF-e do fornecedor, lista de compras por WhatsApp, "
    "contagem pelo celular e perdas com motivo",
    "description": """
Etapa 5 do PRD: saber o que tem, o que falta e quanto custou cada venda.

Nativo (configurado): estoque com custo médio, ficha técnica como lista de materiais do tipo
"kit" (baixa os insumos na venda do PDV via pos_mrp), compras, inventário, sucata, estoque mínimo
e transferência entre armazéns.

Programado aqui:
* CMV por produto, por categoria e por noite (vendas, cortesias, consumo de funcionário e perdas).
* Leitor do XML da NF-e do fornecedor: cria a entrada sem digitação (produtos reconhecidos pelo
  código do fornecedor, pelo código de barras ou criados na hora) e atualiza o custo médio.
* Lista de compras sugerida (abaixo do mínimo), agrupada por fornecedor, com link pronto de WhatsApp.
* Contagem de estoque pelo celular, com diferença e ajuste aprovado pelo gerente.
* Perdas (quebra, vencido, erro de preparo) com motivo e auditoria.
""",
    "version": "18.0.1.0.0",
    "category": "Boteco",
    "author": "Boteco Raiz",
    "license": "LGPL-3",
    "depends": ["boteco_pos", "pos_mrp", "purchase_stock", "mrp"],
    "data": [
        "security/ir.model.access.csv",
        "data/stock_scrap_reason_data.xml",
        "data/ir_cron_data.xml",
        "views/boteco_cmv_views.xml",
        "views/boteco_compras_inteligentes_views.xml",
        "views/boteco_nfe_views.xml",
        "views/boteco_lista_compras_views.xml",
        "views/boteco_contagem_views.xml",
        "views/contagem_templates.xml",
        "views/menus.xml",
    ],
    "assets": {
        "boteco_estoque.assets_contagem": [
            "boteco_base/static/src/css/boteco_tokens.css",
            "boteco_estoque/static/src/contagem/contagem.css",
            "boteco_estoque/static/src/contagem/contagem.js",
        ],
    },
    "installable": True,
}
