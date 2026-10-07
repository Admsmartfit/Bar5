# Etapa 9 – Controle fiscal para emissão posterior (`boteco_fiscal_export`)

> **Decisão pendente do contador** (PRD, seção 10): no varejo a NFC-e normalmente é emitida no momento
> da venda. Este módulo guarda tudo para qualquer resposta; o alerta de pendências usa o prazo
> configurado na empresa (padrão 3 dias).

- Conta paga no bar → registro **NFC-e pendente**; entrega a bar cliente → **NF-e pendente**.
- Cortesia total, consumo de funcionário e perda → **não emitir**, com motivo. Itens de cortesia
  dentro de uma conta normal não entram na nota.
- Boteco › Fiscal › **Vendas e notas**: filtros por situação, tipo e período; pivot por dia.
- **Exportar para emissão:** período, tipo, formato (CSV, Excel, JSON) e layout. Bloqueia e lista os
  produtos sem NCM/CFOP. Cada exportação vira lote numerado (FIS/AAAA/NNNN, arquivo guardado);
  o que já foi exportado só sai de novo marcando "Exportar de novo".
- **Layouts:** ordem e nome das colunas, separador e decimal, para casar com o emissor escolhido
  (decisão pendente do PRD).
- **Importar retorno:** planilha com `referencia` (ou `registro_id`), `numero` e `chave`.

| Critério | Teste |
| --- | --- |
| Exportar uma noite e importar o retorno zera as pendências | `test_exportar_e_importar_retorno_zera_a_noite` |
| O mesmo registro não sai em dois lotes sem ação explícita | `test_mesmo_registro_nao_sai_em_dois_lotes` |
| Soma dos itens exportados bate com o faturamento do dia | `test_soma_dos_itens_bate_com_o_faturamento` (itens + taxa de serviço = vendas do fechamento) |
