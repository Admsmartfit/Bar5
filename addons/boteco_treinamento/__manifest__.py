{
    "name": "Boteco – Modo treinamento",
    "summary": "Instalado só no banco de treino: faixa vermelha em todas as telas e nada é impresso",
    "description": """
Etapa 10 do PRD: modo treinamento com dados de mentira, que não entram no caixa nem no estoque.

O treinamento roda num banco separado (boteco_treino), copiado do banco real pelo
scripts/treinamento.sh e servido em https://boteco.local:8443. Este módulo, instalado só
nesse banco:
* mostra a faixa "MODO TREINAMENTO" no PDV, no tablet/QR, no KDS e no backend;
* não manda nada para as impressoras (tickets e etiquetas só aparecem como impressos);
* desliga backups e e-mails desse banco.
""",
    "version": "18.0.1.0.0",
    "category": "Boteco",
    "author": "Boteco Raiz",
    "license": "LGPL-3",
    "depends": ["boteco_kds", "boteco_autoatendimento"],
    "data": ["data/treino_data.xml"],
    "assets": {
        "web.assets_backend": ["boteco_treinamento/static/src/faixa.scss"],
        "point_of_sale._assets_pos": ["boteco_treinamento/static/src/faixa.scss"],
        "pos_self_order.assets": ["boteco_treinamento/static/src/faixa.scss"],
        "boteco_base.assets_pin": ["boteco_treinamento/static/src/faixa.scss"],
    },
    "post_init_hook": "post_init_hook",
    "installable": True,
}
