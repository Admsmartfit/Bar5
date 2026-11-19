{
    "name": "Boteco – Tablet na mesa e QR Code",
    "summary": "Chamar garçom, pedir a conta, aprovação do celular, segurança do QR, aviso +18, "
    "Minha conta, Pedir de novo e tela de descanso",
    "description": """
Etapa 4 do PRD: o cliente pede sozinho; o garçom só entrega e atende.

Nativo (configurado): autoatendimento do Odoo (pos_self_order) com QR por mesa, cardápio com fotos,
carrinho e envio do pedido.

Programado aqui:
* Segurança do QR: o pedido só sai de dentro da rede Wi-Fi dos clientes; cada abertura de mesa
  gera um código de sessão novo; o primeiro pedido de cada celular precisa de um toque do
  garçom; limite de valor por pedido pelo QR.
* Tablet fixo da mesa (modo quiosque): já liberado; sair só com PIN do gerente; volta para a
  tela de boas-vindas quando a conta fecha; tela de descanso com ofertas depois de 2 minutos.
* Botões fixos "Chamar garçom" e "Pedir a conta" (mudam a cor da mesa no mapa e avisam o garçom).
* "Minha conta": itens com status (na fila, preparando, a caminho), total, taxa e couvert.
* Primeiro item com álcool da mesa: aviso "proibido para menores de 18" e o garçom confirma.
* "Pedir de novo": bebidas já pedidas na mesa com um toque.
* Pedido pronto para envio não se perde sem rede: fica no aparelho e vai quando a rede volta.
* Pedidos do QR e do tablet vão direto para a produção (bar e chapa).
""",
    "version": "18.0.1.0.0",
    "category": "Boteco",
    "author": "Boteco Raiz",
    "license": "LGPL-3",
    "depends": ["boteco_kds", "pos_self_order"],
    "data": [
        "security/ir.model.access.csv",
        "views/boteco_dispositivo_views.xml",
        "views/pos_config_views.xml",
        "views/menus.xml",
        "data/menus_recursos_data.xml",
        "data/boteco_ajuda_artigos.xml",
    ],
    "assets": {
        "pos_self_order.assets": [
            "boteco_base/static/src/css/boteco_tokens.css",
            "boteco_autoatendimento/static/src/self_order/**/*",
        ],
        "point_of_sale._assets_pos": [
            "boteco_autoatendimento/static/src/pos/**/*",
        ],
    },
    "installable": True,
}
