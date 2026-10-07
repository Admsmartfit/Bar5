# Etapa 2 – Salão, contas e caixa (`boteco_pos`)

## Nativo x programado

- **Nativo (configurado):** mapa de mesas, transferir e juntar mesas, dividir conta por item, várias
  formas de pagamento e troco, comanda avulsa (pedido sem mesa), abertura/fechamento de sessão,
  entrada e saída de dinheiro, pré-conta.
- **Programado:**
  - Couvert por pessoa nos dias marcados em "Música e couvert" (entra sozinho na conta).
  - Taxa de serviço 10% (configurável) calculada sobre o consumo; "Tirar taxa" pede motivo e
    permissão/PIN e fica na auditoria.
  - Cancelamento de item **já enviado**: motivo da lista + PIN do gerente. O servidor confere de novo
    na sincronização (não dá para burlar pela tela) e também quando a conta inteira é cancelada.
  - Desconto e cortesia: motivo + PIN; o servidor exige a autorização de uso único.
  - Consumo de funcionário: a preço de custo ou zero, com PIN.
  - Sangria/reforço com motivo e permissão (o caixa faz; o garçom precisa do PIN).
  - Contagem cega: o operador digita o que contou antes de ver o esperado; o resultado fica em
    "Fechamentos de caixa" com PDF para assinar. Não fecha com mesa aberta.
  - Mapa de mesas com cor por situação (livre, ocupada, chamou, pediu a conta – roxo, esperando
    pagamento, atrasada – vermelho) e minutos desde o último pedido.
  - Dividir igual (centavos distribuídos sem sobra) e CPF/CNPJ na nota (validado).
- O servidor descarta os campos que só ele controla quando o PDV sincroniza (o PDV devolve tudo o
  que carregou, inclusive valores antigos).

## Critérios de aceite

| Critério | Teste | Verificado no navegador |
| --- | --- | --- |
| Conta de 4 dividida em 3 PIX e 1 cartão fecha com saldo zero | `test_conta_de_4_dividida_em_3_pix_e_1_cartao_fecha_zerada` | botões "Dividir igual" e "CPF na nota" na tela de pagamento |
| Item cancelado após envio sem PIN é bloqueado | `test_item_enviado_cancelado_sem_pin_e_bloqueado`, `test_cancelar_conta_inteira_exige_pin` | ⌫ num item enviado abre motivo + PIN; após confirmar, a auditoria registrou "Cancelado: 2 x Long neck – mesa 3, Erro do garçom, R$ 24,00" |
| Fechamento mostra diferença contado x esperado por forma | `test_fechamento_cego_mostra_diferenca_por_forma` | — |
| Garçom abre mesa e lança 3 itens em menos de 20 s | — | **Pendente: cronometrar com garçom real** (no fluxo: mesa → 3 toques nos itens → "Pedido") |

Total: 26 testes no módulo.
