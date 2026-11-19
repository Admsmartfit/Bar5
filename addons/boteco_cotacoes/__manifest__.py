{
    "name": "Boteco – Cotações pela API e radar de oportunidades",
    "version": "18.0.2.0.1",
    "category": "Inventory/Purchase",
    "summary": "Recebe cotações limpas do serviço externo (n8n) e gera oportunidades de compra e ideias de promoção",
    "description": """
19/11/2026 — o Odoo não fala mais com WhatsApp, sites, Instagram nem fotos. Isso fica num serviço externo
(n8n + Evolution API + IA), que manda só dados limpos por uma API com token.

* POST /api/boteco/webhook/cotacao_recebida: fornecedor, produto (código interno ou de barras), unidade e preço.
* Grava no radar de preços, atualiza o preço do fornecedor e o pedido de cotação em aberto.
* Oportunidade de compra: preço X% abaixo do preço médio ponderado das últimas 3 compras -> aviso ao gerente,
  sugestão de compra maior na Lista de compras e ideias de Oferta relâmpago com a margem calculada.
* O que não for reconhecido vai para "Cotações para revisar".
""",
    "author": "Boteco Raiz",
    "license": "LGPL-3",
    "depends": ["boteco_painel"],
    "data": [
        "security/ir.model.access.csv",
        "data/ir_cron_data.xml",
        "data/remover_whatsapp_data.xml",
        "views/cotacoes_views.xml",
        "data/boteco_ajuda_artigos.xml",
    ],
    "installable": True,
}
