# Etapa 3 – Produção no bar e na chapa (`boteco_kds`)

## Decisões

- A tela de cozinha do Odoo é da versão paga; esta foi escrita do zero em OWL, com o fluxo do Mosaic
  do URY só como referência (licença AGPL: nenhum código copiado).
- **Tudo nasce no servidor:** quando o PDV "manda pra cozinha", o servidor compara o que já tinha
  processado com o novo envio e cria os tickets por setor. Vale para garçom, tablet e QR.
- **Impressão pelo servidor** (ESC/POS, porta 9100), em fila: o ticket é enviado logo após gravar o
  pedido; se a impressora estiver desligada, fica esperando e sai **na ordem** quando ela voltar
  (cron a cada minuto). A tela e a página de saúde avisam. Não configure as "impressoras de pedido"
  nativas do PDV junto, para não sair ticket em dobro.

## Como usar

- Chapeiro: entra com PIN e cai na "Fila da chapa". Toque no cartão = começar / pronto.
  "Desfazer" por 5 s. Toque longo = reimprimir. "Tela cheia" esconde o menu.
- Garçom: sino com contador no PDV ("Prontos para entregar") e aviso com som quando fica pronto.
- Gerente: alerta fixo quando um pedido passa de 30 min; "Tempos de produção" (pivot por produto e hora).

## Critérios de aceite

| Critério | Teste |
| --- | --- |
| Cerveja e porção em 2 impressoras diferentes em até 2 s | `test_cerveja_e_porcao_em_duas_impressoras_em_ate_2s` (impressoras simuladas na rede) |
| Desligar e religar a impressora não perde ticket | `test_impressora_desligada_nao_perde_ticket` (confere também a ordem) |
| Pedido parado há 31 min fica vermelho e alerta o gerente | `test_pedido_parado_31_min_alerta_gerente` |
| Tela da chapa sem teclado e sem mouse | Botões de 64 px, toque/toque longo; verificado no navegador (cartões por setor, cronômetro, "Desfazer") |

**Pendente:** repetir o primeiro e o segundo critério com as duas térmicas reais.
