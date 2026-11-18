{
    "name": "Boteco – Salão e Caixa",
    "summary": "Couvert, taxa de serviço, cancelamento/desconto/cortesia com PIN do gerente, consumo de "
    "funcionário, contagem cega, cores das mesas e divisão da conta",
    "description": """
Etapa 2 do PRD: operar uma noite inteira só com garçom e caixa.

Nativo do Odoo (configurado): mapa de mesas, transferir e juntar mesas, dividir conta por item,
várias formas de pagamento, abertura e fechamento de sessão, entrada e saída de dinheiro.

Programado aqui:
* Couvert artístico por pessoa, ligado nos dias de música (agenda).
* Taxa de serviço de 10% sugerida; tirar exige permissão (ou PIN do gerente) e fica registrado.
* Cancelamento de item já enviado só com PIN do gerente e motivo da lista – validado também no
  servidor (não dá para burlar pela tela).
* Desconto e cortesia com PIN do gerente e motivo.
* Consumo de funcionário a preço de custo ou zero.
* Sangria e reforço com motivo e permissão.
* Contagem cega no fechamento: o operador digita o que contou antes de ver o esperado.
* Não deixa fechar o caixa com mesa aberta.
* Mapa de mesas com cor por situação e tempo desde o último pedido.
* Dividir a conta em partes iguais; CPF na nota (para a emissão posterior).
""",
    "version": "18.0.1.0.0",
    "category": "Boteco",
    "author": "Boteco Raiz",
    "license": "LGPL-3",
    "depends": ["boteco_cardapio", "pos_restaurant"],
    "data": [
        "security/ir.model.access.csv",
        "security/boteco_pos_security.xml",
        "data/boteco_motivo_data.xml",
        "data/product_data.xml",
        "data/boteco_tag_rapida_data.xml",
        "views/boteco_motivo_views.xml",
        "views/boteco_canais_views.xml",
        "views/portaria_templates.xml",
        "views/boteco_agenda_musica_views.xml",
        "views/boteco_fechamento_caixa_views.xml",
        "views/pos_config_views.xml",
        "views/pos_order_views.xml",
        "report/fechamento_caixa_report.xml",
        "views/menus.xml",
    ],
    "assets": {
        "point_of_sale._assets_pos": [
            "boteco_pos/static/src/**/*",
        ],
    },
    "installable": True,
}
