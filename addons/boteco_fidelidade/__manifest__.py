{
    "name": "Boteco – Fidelidade e cashback",
    "version": "18.0.1.0.0",
    "category": "Sales/Point of Sale",
    "summary": "Cartão fidelidade (10 chopes = 1 grátis), cashback e cupom de aniversário com o loyalty gratuito",
    "description": """
Etapa 31 (PRD de recursos avançados). Usa os módulos gratuitos do Odoo (loyalty + pos_loyalty):

* Programas modelo (desligados até o dono ligar): 10 chopes = 1 grátis, cashback de 5% e cupom de aniversário.
* Cliente identificado pelo celular (sem cartão físico).
* O chope grátis entra sozinho na conta quando o cliente completa os pontos.
* Não acumula com happy hour / oferta relâmpago (configurável) e não vale em consumo de funcionário.
* Tablet / QR: "Minha conta" mostra o saldo do cliente da mesa.
* Régua de aniversariantes: a mensagem já leva o código do cupom.
* Chave "Fidelidade / cashback" na Central de Recursos: desligada, o PDV não oferece programas.
""",
    "author": "Boteco Raiz",
    "license": "LGPL-3",
    "depends": ["boteco_autoatendimento", "pos_loyalty"],
    "data": [
        "security/ir.model.access.csv",
        "data/fidelidade_data.xml",
        "views/loyalty_views.xml",
        "data/boteco_ajuda_artigos.xml",
    ],
    "assets": {
        "point_of_sale._assets_pos": [
            "boteco_fidelidade/static/src/pos/**/*",
        ],
        "pos_self_order.assets": [
            "boteco_fidelidade/static/src/self_order/**/*",
        ],
    },
    "installable": True,
}
