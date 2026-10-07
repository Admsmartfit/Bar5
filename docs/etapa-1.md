# Etapa 1 – Cadastros e cardápio (`boteco_cardapio`)

## Nativo x programado

- **Nativo:** produtos, categorias do PDV com foto, atributos (adicionais com preço extra), combos,
  listas de preço, plantas de mesas, QR por mesa do autoatendimento, "disponível no autoatendimento".
- **Programado:** happy hour por dias/horário com troca exata no tablet, QR e caixa; oferta relâmpago
  com limite e "Lançar agora"; botão "Acabou" (usa o aviso em tempo real do próprio Odoo); +18;
  dados fiscais (NCM, CEST, CFOP, CST/CSOSN, origem, unidade) com aviso amarelo, padrões por categoria
  e relatório de pendências; foto recortada em quadrado (1024 px); cadastro rápido numa tela;
  QR das mesas em PDF; importar/exportar cardápio em Excel.
- O servidor também aplica o preço promocional nos pedidos do tablet/QR (o Odoo recalcula preço
  no servidor) e **trava** o preço da linha no momento do pedido: chope pedido às 20h59 continua
  com preço de happy hour depois das 21h.

## Critérios de aceite

| Critério | Teste automático | Manual |
| --- | --- | --- |
| 20h59 mostra happy hour; 21h00 preço normal, sem recarregar | `test_20h59_happy_21h00_normal`, `test_proxima_troca_exata`, `test_estado_para_o_tablet` | Mudar o happy hour para terminar daqui a 2 min e deixar o tablet aberto: o preço muda sozinho no minuto exato (a tela agenda a troca pela hora do servidor). |
| Oferta de 20 unidades some ao vender a 20ª | `test_some_ao_vender_a_vigesima` | Cardápio › Ofertas relâmpago › Lançar agora; vender 20 |
| Cadastro de produto em menos de 1 minuto | `test_cadastro_rapido_numa_tela` (campos mínimos) | **Pendente: cronometrar com alguém que nunca usou** |
| Relatório "Produtos sem dados fiscais" lista os pendentes | `test_dados_fiscais_e_relatorio_de_pendencias` | Cardápio › Produtos sem dados fiscais |

Total: 24 testes no módulo.

## Seção 4

Cadastro rápido: nome, preço, categoria, "vai para" (bar/chapa) e foto na mesma tela; fiscal no
mesmo formulário com a categoria preenchendo o padrão. Kanban com foto e etiquetas ACABOU / +18 /
fiscal pendente.
