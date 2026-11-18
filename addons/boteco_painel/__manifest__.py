{
    "name": "Boteco – Painel do dono e financeiro",
    "summary": "Painel da noite em tempo real, metas do plano, DRE por frente, fechamento do dia (redução Z) "
    "e fluxo de caixa",
    "description": """
Etapa 8 do PRD.

Nativo (configurado): contas a pagar e a receber, conciliação bancária, relatórios do PDV e de vendas,
exportação para Excel.

Programado aqui:
* Painel do dono numa tela (atualiza sozinho a cada 30 s): faturamento da noite, clientes, ticket médio,
  CMV, itens mais vendidos, tempo médio de entrega, cancelamentos e cortesias, comparação com a mesma
  noite da semana anterior, contas vencidas.
* Indicadores do plano x meta: clientes por noite (ponto de equilíbrio 86), kg vendidos a outros bares,
  bares com assessoria.
* DRE simples por frente (bar, tira-gosto B2B, assessoria), com taxa de cartão por forma de pagamento.
* Fechamento do dia ("redução Z"): vendas, formas de pagamento, cancelamentos, descontos, cortesias,
  taxa de serviço, couvert e diferença de caixa. PDF e Excel.
* Fluxo de caixa previsto (a receber e a pagar em aberto) x realizado.
""",
    "version": "18.0.1.0.0",
    "category": "Boteco",
    "author": "Boteco Raiz",
    "license": "LGPL-3",
    "depends": ["boteco_b2b", "boteco_estoque", "boteco_kds"],
    "data": [
        "security/ir.model.access.csv",
        "views/res_company_views.xml",
        "views/pos_payment_method_views.xml",
        "views/painel_views.xml",
        "views/boteco_rateio_views.xml",
        "report/fechamento_dia_report.xml",
        "report/dre_report.xml",
        "views/menus.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "boteco_painel/static/src/**/*",
        ],
    },
    "installable": True,
}
