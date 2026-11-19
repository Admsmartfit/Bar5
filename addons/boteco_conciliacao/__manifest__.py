{
    "name": "Boteco – Conferência de cartões e Pix",
    "version": "18.0.1.0.0",
    "category": "Accounting",
    "summary": "Recebíveis de cartão/Pix, extrato da maquininha e do banco, taxa contratada x cobrada, repasse atrasado",
    "description": """
Etapa 28 (PRD de recursos avançados), sem contabilidade paga:

* Maquininhas com a tabela de taxas e prazos por modalidade (débito, crédito, parcelado, Pix).
* Cada pagamento de cartão/Pix do caixa vira um recebível previsto (bruto, taxa, líquido, data).
* Importa o extrato da maquininha (CSV/Excel, cabeçalho reconhecido sozinho ou configurado) e do banco (OFX).
* Casa recebível x extrato por valor, data e NSU; o que sobra vai para "Conferir".
* Alertas: taxa acima da contratada (com o valor pago a mais), repasse atrasado, venda sem registro, estorno, Pix sem venda.
* Card "Cartões e Pix" no Painel do dono e o confirmado pela maquininha no caixa.
""",
    "author": "Boteco Raiz",
    "license": "LGPL-3",
    "depends": ["boteco_painel"],
    "data": [
        "security/ir.model.access.csv",
        "data/ir_cron_data.xml",
        "views/conciliacao_views.xml",
        "views/central_views.xml",
        "data/boteco_ajuda_artigos.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "boteco_conciliacao/static/src/**/*",
        ],
    },
    "installable": True,
}
