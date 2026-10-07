# Etapa 7 – Venda a outros bares e assessoria (`boteco_b2b`)

- Bar cliente: marcar "Bar cliente (B2B)" no contato, com CNPJ, IE, endereço, tabela de preço
  (padrão "Bares clientes – R$ 42/kg", para a categoria "Tira-gosto (venda a bares)") e prazo.
- Pedido: produtos em kg e data de entrega; "Repetir último pedido" com um toque no cliente;
  pedidos recorrentes (ex.: toda quinta, 20 kg) criados sozinhos na véspera.
- Separação lendo o QR das etiquetas (registra os lotes); romaneio em PDF com assinatura.
- Ao entregar, a fatura nasce e é lançada com o prazo do cliente (contas a receber).
- Assessoria: contrato com implantação (R$ 3.500) cobrada ao ativar e mensalidade (R$ 450) gerada
  todo mês com antecedência, vencendo no dia combinado.
- Cliente que passou do prazo sem comprar vira atividade "ligar" para o comercial.

| Critério | Teste |
| --- | --- |
| Pedido separado registra os lotes e aparece no rastreio | `test_pedido_separado_registra_lote_rastreio_e_fatura` |
| Contrato gera a mensalidade do mês seguinte | `test_contrato_gera_mensalidade_do_mes_seguinte` |
| Todo pedido B2B entregue entra como pendente no fiscal | `test_entrega_b2b_gera_nfe_pendente` (módulo da etapa 9) |
