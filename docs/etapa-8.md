# Etapa 8 – Financeiro, relatórios e painel do dono (`boteco_painel`)

- **Painel do dono** (tela inicial do dono, funciona no celular): faturamento da noite (inclui contas
  abertas), clientes, ticket médio, CMV, tempo médio de preparo e pedidos atrasados, cancelamentos,
  descontos e cortesias, mais vendidos, comparação com a mesma noite da semana anterior, metas do
  plano (86 clientes/noite, kg vendidos a bares, bares com assessoria – editáveis na empresa),
  contas vencidas e alertas. Atualiza sozinho a cada 30 s.
- **Fechamento do dia (redução Z):** vendas, contas, clientes, formas de pagamento, taxa, couvert,
  descontos, cortesias, consumo de funcionários, sangrias, cancelamentos com motivo e quem autorizou,
  contagem dos caixas e diferença. PDF e Excel.
- **DRE por frente:** bar (contas do PDV sem a taxa de serviço; custo = CMV; taxas de maquininha
  configuradas em cada forma de pagamento), B2B (faturas; custo = valor de estoque entregue) e
  assessoria (faturas dos contratos). Contas a pagar podem ser marcadas com a frente ou "geral".
- **Fluxo de caixa:** a receber e a pagar em aberto por semana (30 dias) × recebido e pago.
- Exportação: qualquer lista do Odoo exporta para Excel; relatórios do boteco têm PDF.
- Acesso fora do bar: pela VPN ([vpn.md](vpn.md)).

| Critério | Teste |
| --- | --- |
| Painel mostra a noite em tempo real | `test_painel_mostra_a_noite_em_tempo_real` + atualização automática (verificado no navegador) |
| DRE do mês separa as três frentes | `test_dre_separa_as_tres_frentes` |
| Relatório do dia bate com os fechamentos de caixa | `test_relatorio_do_dia_bate_com_os_fechamentos_de_caixa` |

Conciliação: o fechamento de sessão do PDV já gera os lançamentos por forma de pagamento (nativo);
a taxa de cartão entra como despesa na DRE pelo percentual cadastrado.
