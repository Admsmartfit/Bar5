# Etapa 5 – Estoque e compras do bar (`boteco_estoque`)

- **Ficha técnica:** lista de materiais do tipo **kit** no produto do cardápio (ex.: porção = 12
  bolinhos + 0,03 kg de molho). A venda no PDV baixa os insumos (nativo `pos_mrp`). O módulo corrige o
  custo do kit para a soma dos insumos (o Odoo usaria o custo cadastrado do kit, normalmente zero).
- **CMV:** Boteco › Estoque e compras › CMV (pivot por dia, produto, categoria e tipo: venda,
  cortesia, funcionário, perda).
- **Entrada por XML da NF-e:** sobe o XML, confere e "Dar entrada". Fornecedor e insumos são
  reconhecidos (código do fornecedor, código de barras) ou criados; o fator (ex.: caixa com 24) é
  ensinado uma vez e fica salvo. A mesma nota não entra duas vezes. Custo médio atualizado.
- **Lista de compras:** abaixo do mínimo, por fornecedor, com link pronto de WhatsApp.
- **Contagem pelo celular:** contagem cega (a tela não mostra o que o sistema tem), salva sozinha;
  o gerente aprova o ajuste, que vai para a auditoria.
- **Perdas:** sucata nativa com motivo obrigatório (quebra, vencido, erro de preparo) e permissão.

| Critério | Teste |
| --- | --- |
| Vender 10 porções baixa exatamente a ficha técnica | `test_vender_10_porcoes_baixa_exatamente_a_ficha_tecnica` |
| Importar XML cria a entrada sem digitação | `test_importar_xml_da_nota_cria_entrada_sem_digitacao` (XML de exemplo em `tests/dados`) |
| CMV da noite bate com a soma dos custos | `test_cmv_da_noite_bate_com_os_custos` |
