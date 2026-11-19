{
    "name": "Boteco – Cotações por WhatsApp e coletor de ofertas",
    "version": "18.0.1.0.0",
    "category": "Inventory/Purchase",
    "summary": "WhatsApp do bar por QR Code (Evolution API) e coletor externo de sites/Instagram alimentando o radar de preços",
    "description": """
Etapa 35 (PRD de recursos avançados):

* Tela "WhatsApp (conectar)": QR Code como no WhatsApp Web (Evolution API em contêiner próprio, rede interna).
* Webhook com token: só mensagens de fornecedores cadastrados e confiáveis viram cotação; o resto é descartado sem gravar.
* Leitura em fila (texto, PDF, foto) com o mesmo parser da Etapa 18; de-para que aprende; preço do fornecedor no produto.
* "Cotações para revisar" para o que não casou; "Ofertas encontradas"; melhor preço e fonte na Lista de compras.
* API do coletor externo (sites com Playwright e Instagram 1x por dia), fora do servidor do PDV.
* Avisos de WhatsApp desconectado no Painel do dono e na Saúde do sistema; registro de cada chamada.
""",
    "author": "Boteco Raiz",
    "license": "LGPL-3",
    "depends": ["boteco_painel"],
    "external_dependencies": {"python": ["requests"]},
    "data": [
        "security/ir.model.access.csv",
        "data/ir_cron_data.xml",
        "views/cotacoes_views.xml",
        "data/boteco_ajuda_artigos.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "boteco_cotacoes/static/src/**/*",
        ],
    },
    "installable": True,
}
