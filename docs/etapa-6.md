# Etapa 6 – Cozinha central (`boteco_cozinha_central`)

- **Receita:** lista de materiais "fabricar" com rendimento, perda esperada, tempo e modo de preparo;
  no produto: "Produzido na cozinha central", conservação e validade (dias). O produto passa a ter
  lote e validade automaticamente.
- **Plano de produção:** sugere o que produzir (saída média do mesmo dia da semana nas últimas 4
  semanas × dias de cobertura + pedidos B2B em aberto − estoque − o que já está em produção),
  arredondado em receitas inteiras; um botão cria as produções.
- **Tela do tablet:** "Produção do dia" → toque na produção → **Iniciar** → teclado de peso →
  **Finalizar e imprimir etiqueta**. Gera o lote `CCAAMMDD-NNN`, validade, baixa a receita inteira,
  registra o rendimento real e imprime a etiqueta (ZPL ou TSPL) com produto, fabricação, validade,
  lote, peso, conservação, empresa, CNPJ, registro sanitário e QR.
- **Transferência para o bar e entregas B2B:** "Separar lendo QR" (leitor ou câmera do celular),
  lote vencido é recusado; no bar, "Confirmar recebimento".
- **Lotes:** amarelo quando vence em até 3 dias; vencido bloqueado em qualquer movimentação
  (só perda). Saída FEFO (ligada pelo instalador).
- **Temperatura:** registro diário por equipamento, fora da faixa em vermelho com ação corretiva,
  PDF da planilha da Vigilância.
- **Rastreio:** busca pelo código do lote mostra os insumos usados e todos que receberam.

| Critério | Teste |
| --- | --- |
| Finalizar imprime a etiqueta em até 3 s | `test_finalizar_gera_lote_baixa_insumos_e_imprime_etiqueta_em_3s` (impressora simulada) |
| Transferir lote vencido é bloqueado | `test_lote_vencido_nao_pode_ser_transferido` |
| Busca por lote mostra todos os clientes | `test_rastreio_mostra_insumos_e_clientes` |
| Cozinheiro conclui sem teclado, exceto o peso | Tela de 3 botões com teclado numérico próprio (verificada no navegador) |

**Pendente:** imprimir na impressora de etiquetas real e ajustar posições do ZPL ao rolo usado
(100 × 70 mm configurado). Incluir o registro sanitário na empresa quando sair.
