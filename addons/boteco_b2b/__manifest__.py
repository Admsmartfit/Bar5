{
    "name": "Boteco – Venda a outros bares e assessoria",
    "summary": "Tira-gosto por quilo para outros bares com rastreio de lote, pedido recorrente, romaneio, "
    "contas a receber e contratos de assessoria com mensalidade automática",
    "description": """
Etapa 7 do PRD.

Nativo (configurado): clientes, listas de preço por cliente, pedidos de venda, entrega com lote,
faturas e contas a receber.

Programado aqui:
* Cliente B2B com dados fiscais (CNPJ, IE, endereço) para a nota posterior.
* Tabela de preço padrão de R$ 42/kg (editável por cliente).
* Pedido recorrente (ex.: toda quinta, 20 kg de bolinho) e "Repetir último pedido" com um toque.
* Separação lendo o QR das etiquetas (registra os lotes enviados – módulo da cozinha central).
* Romaneio de entrega impresso com espaço para assinatura de recebimento.
* Conta a receber gerada na entrega, com o prazo do cliente.
* Assessoria: contrato por bar com implantação (R$ 3.500) e mensalidade (R$ 450) gerando as
  cobranças todo mês.
* Histórico de compras e alerta de cliente que parou de comprar.
""",
    "version": "18.0.1.0.0",
    "category": "Boteco",
    "author": "Boteco Raiz",
    "license": "LGPL-3",
    "depends": ["boteco_cozinha_central", "sale_management", "sale_stock", "account"],
    "data": [
        "security/ir.model.access.csv",
        "data/b2b_data.xml",
        "data/ir_cron_data.xml",
        "views/res_partner_views.xml",
        "views/boteco_recorrencia_views.xml",
        "views/boteco_contrato_views.xml",
        "views/sale_order_views.xml",
        "report/romaneio_report.xml",
        "views/menus.xml",
        "data/b2b_recursos_data.xml",
    ],
    "installable": True,
}
