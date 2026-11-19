# Auditoria de QA, arquitetura e UX — Sistema Boteco (Odoo 18)

*19/11/2026. Base: leitura do código atual (`addons/boteco_*`), suíte automática (265 testes passando) e testes no navegador da instância de desenvolvimento.*

**Legenda**
* ✅ **Verificado:** confirmado no código ou num teste.
* ⚠️ **Risco:** o código permite; precisa de teste físico.
* 💡 **Recomendação**

Achados que **já estavam protegidos** aparecem como ✅. Isso evita gastar esforço com o que já funciona.

---

## SEÇÃO 1 — Sumário executivo de riscos

| # | Risco | Onde | Gravidade |
|---|---|---|---|
| 1 | **Cliente e garçom discordam do preço na virada do happy hour.** O preço vale o do momento em que o pedido chega ao servidor, não o do momento em que entrou no carrinho. No fim do happy hour (20h59 no carrinho, enviado 21h01), o cliente viu R$ 6,90 e paga R$ 9,90 sem aviso. | `boteco_cardapio/models/pos_order.py` (`boteco_preco_fixado` é gravado no `create` da linha); `estado_cardapio.js` | **Alta** (atrito no balcão, avaliação ruim) |
| 2 | **Custo errado por arredondamento.** A precisão "Product Price" é **2 casas** e "Product Unit of Measure" também. Uma caixa de 12 L virando doses de 50 ml dá custo de R$ 0,4166 por dose, gravado como R$ 0,42 (+0,8% em cada dose). Uma ficha técnica com 36 g guardada em kg vira 0,04 kg (+11% de consumo). Isso distorce CMV, ponto de pedido e DRE ao longo dos meses. | banco (`decimal_precision`); `boteco_nfe_importacao.py:142,172`; `mrp_bom.py` | **Alta** (financeiro) |
| 3 | **A quarentena interrompe todos os garçons ao mesmo tempo.** Cada pedido retido e cada celular pedindo liberação abre uma **janela que bloqueia o PDV** em **todos** os tablets do salão, com som. No pico de sexta, o garçom perde o fluxo no meio de um pedido. | `boteco_autoatendimento/static/src/pos/aprovacoes.js` (`dialog.add(QuarentenaDialog)`, `ConfirmationDialog`) | **Alta** (velocidade no pico) |

Corrigido durante esta auditoria: **a página de ponto `/boteco/ponto` listava os nomes da equipe para qualquer pessoa na internet.** Isso permitia descobrir quem trabalha no bar e bloquear o PIN de cada um (5 erros = 15 min bloqueado). Agora ela só abre na rede da equipe, como a tela de PIN, e há um teste para isso.

---

## SEÇÃO 2 — Bugs e riscos de back-end e banco

| Módulo | Problema | Impacto no negócio | Solução recomendada |
|---|---|---|---|
| `boteco_autoatendimento` | ✅ **Pedido duplicado por Wi-Fi instável:** o `pos.order.uuid` tem `unique` no banco. Dois envios do mesmo carrinho viram uma atualização do mesmo pedido, e o Odoo repete a transação em caso de conflito. | — | Nada a fazer. Manter o teste. |
| `boteco_autoatendimento` | ✅ **Dois garçons aprovando a mesma quarentena:** `_boteco_travar_retido()` faz `SELECT … FOR UPDATE`, e o segundo recebe "já resolvido". | — | Nada a fazer. |
| `boteco_autoatendimento` | ⚠️ **Celular liberado por um garçom continua com a janela "Liberar?" aberta nos outros tablets.** O `BOTECO_APROVAR` não tem evento de fechamento, ao contrário da quarentena (`BOTECO_ANOMALIA_RESOLVIDA`). | Janelas velhas se acumulam no pico. | Enviar `BOTECO_DISPOSITIVO_RESOLVIDO` em `boteco_dispositivo.boteco_aprovar()` e fechar a janela em `aprovacoes.js`, como já é feito em `botecoFecharQuarentena`. |
| `boteco_autoatendimento` | ⚠️ **Pedido recusado na quarentena some da "Minha conta" sem explicação.** `action_boteco_rejeitar_pedido` remove as linhas e cancela o pedido, mas o celular ou tablet não recebe nenhuma mensagem (não há tratamento de "recusado" em `self_order_patch.js`). | O cliente acha que o sistema "comeu" o pedido e chama o garçom irritado. | No `_boteco_finalizar_resolucao`, notificar o aparelho pelo canal da mesa (`BOTECO_MESA` com `evento: "pedido_recusado"` e o motivo). No `boteco_mesa.js`, mostrar um aviso fixo: "O garçom vai falar com você sobre o último pedido". Para "aprovado": "Pedido confirmado e enviado". |
| `boteco_cozinha_central` | ⚠️ **Leitura dupla do mesmo lote no mesmo instante.** `stock_picking.boteco_ler_lote` barra lote já lido (`ja_lido`), mas sem trava: duas leituras simultâneas (leitor que dispara duas vezes) passam juntas pela verificação e criam duas linhas, dobrando a quantidade separada. | Baixa de estoque em dobro e lote "sumindo" no inventário. | No começo do método, `self.env.cr.execute("SELECT id FROM stock_move WHERE id = %s FOR UPDATE", [move.id])` e depois refazer a leitura das linhas. No front, ignorar a mesma leitura repetida em menos de 800 ms. |
| `boteco_cozinha_central` | ⚠️ **Estoque negativo permitido.** Nada impede a ordem de produção de consumir insumo sem saldo; o Odoo deixa ficar negativo por padrão. | CMV e estoque falsos: produziu sem matéria-prima registrada. | Em `mrp_production.py`, antes de concluir, alertar com o que falta (a Etapa 6 já calcula "matéria-prima faltante" com o fator de cocção) e exigir confirmação do gerente com PIN (`boteco.autorizacao`) para concluir com saldo negativo. Registrar na auditoria. |
| `boteco_estoque` | ✅/⚠️ **CMV com fuso e virada do dia fixos.** A parte de perdas da view SQL de `boteco_cmv.py:68` usa `AT TIME ZONE 'America/Sao_Paulo' - INTERVAL '6 hours'`, ignorando `res.company.boteco_hora_virada` e o fuso da empresa. | Se o dono mudar a virada para 5h, uma perda das 5h30 cai em dias diferentes no CMV e no Painel. | Gerar a view com a hora de virada da empresa (gravar a coluna `dia` da perda no `stock.scrap` ao validar, calculada por `company.boteco_dia_operacao()`, como já é feito no `pos.order`). |
| `boteco_estoque` | ⚠️ **Precisão de 2 casas** (ver Risco 2). Em `boteco_nfe_importacao.py:172`, `price_unit = valor_total / quantidade` perde centavos (R$ 100 ÷ 3 = 33,33, e o total fica 99,99). | Diferença de centavos por nota e custo médio errado. | Subir "Product Price" para **4 casas** e "Product Unit of Measure" para **3 casas** com uma migração no `boteco_base`. Na importação, jogar a diferença de arredondamento na última linha para o total bater com a NF-e. |
| `boteco_estoque` | ⚠️ **Fator de conversão digitado à mão sem conferência** (`boteco_nfe_produto.fator`). Errar 12 em vez de 240 (caixa de 12 L em doses) multiplica o custo por 20. | CMV falso por meses, sem ninguém perceber. | Ao gravar o de-para, comparar o custo resultante com o último custo do produto; se variar mais de 50%, mostrar "Confere? 1 caixa = 240 doses → R$ 0,42 por dose (antes R$ 0,40)". Sugerir o fator pela unidade (L → ml) quando as duas estiverem cadastradas. |
| `boteco_conciliacao` | ⚠️ **Dois calendários convivendo.** O recebível usa a data **civil** da venda (correto: a maquininha também usa), mas o Painel e a DRE usam o **dia de operação** (vira às 6h). Uma venda de 02h do dia 1º cai em "mês anterior" na DRE e em "mês atual" no card de taxa. | Pequena diferença entre o card "taxa do mês" e a DRE na virada do mês. | Guardar os dois no recebível (`data_venda` civil para casar com a maquininha e `dia_operacao` para relatórios) e usar `dia_operacao` no card do Painel. |
| `boteco_escala` | ✅ **"Turno vampiro" (passa da meia-noite):** o turno "Noite 17–01" vira início e fim reais em `boteco.turno._intervalo`, e a previsão usa `boteco_dia_operacao` (sexta 01h conta como sexta). As vendas das 03h entram no dia de operação anterior pela virada das 6h. | — | Manter. Documentar que a virada (Configuração › Empresa › Boteco) precisa ser **depois** do último fechamento. |
| `boteco_escala` | ⚠️ **Dobra no mesmo dia** (almoço 11–16 e noite 17–01): uma entrada atrasada no almoço às 13h30 cai também na janela da noite (que olha 4 h antes do início), e as horas são contadas nos dois turnos em `ponto.py → action_gerar`. | Hora extra inflada na folha. | Casar cada batida com **um** turno só (o de início mais próximo) e marcar a presença como usada. |
| `boteco_base` | ⚠️ **Bloqueio de PIN por pessoa, não por aparelho.** 5 erros = 15 min bloqueado (`boteco_pin_tentativa.py`). No tablet compartilhado, um colega errando o PIN "da Ana" a deixa 15 min sem trabalhar no pico. | Garçom parado na sexta à noite. | Bloquear por **pessoa + aparelho** (IP/cookie). Mostrar o contador "2 de 5 tentativas". Deixar o gerente desbloquear com um toque no PDV (o `action_boteco_desbloquear_pin` já existe; falta um botão na tela de PIN). |
| `boteco_cardapio` (OWL) | ✅ **Sem risco de redesenho infinito:** o estado de preço fica fora do sistema reativo (`estado_cardapio.js:16`). O objeto reativo só é alterado por timer ou websocket (`atualizar`, linha 100) e lido em `pos_store_cardapio.js:19`, sem escrita durante o render. | — | Manter a regra: nunca alterar `botecoCardapio` dentro de getter ou de `get_price`. |
| Segurança | ✅ **Rotas públicas:** `/reservar` (CSRF, campo-isca anti-robô, limite por IP), webhook do WhatsApp e API do coletor (token comparado com `consteq`, limite por minuto, HTTPS fora da rede interna), `/boteco/pin` (só na rede da equipe). `/boteco/ponto` foi corrigida. | — | Revisar a cada rota nova: **toda página pública que lista pessoas precisa da trava de rede.** |

---

## SEÇÃO 3 — Atritos de uso (garçom e caixa no pico de sexta)

| # | Momento | Atrito | Inspiração | Mudança proposta |
|---|---|---|---|---|
| 1 | Lançando pedido da mesa 12 | A janela de quarentena ou de "liberar celular" **trava a tela** no meio do pedido, em todos os tablets. | **Toast** (fila de notificações) | Trocar a janela por uma **bandeja de pendências**: um selo vermelho no topo do PDV ("2 pendências") que abre uma gaveta lateral. Só para o garçom **daquela mesa** ou de quem está livre. A janela só aparece se ninguém resolver em 60 s. |
| 2 | Cliente reclama do preço do chope às 21h01 | O preço mudou entre o carrinho e o envio, sem aviso. | **Square** (confirmação clara de preço) | No carrinho do QR: faixa "Happy hour acaba em 4 min". Ao enviar depois da troca: "O preço do chope mudou para R$ 9,90. Confirmar?". Política opcional na Central: "tolerância de 5 min" (vale o preço do momento em que entrou no carrinho). |
| 3 | PIN errado na correria | A tela treme, mas não diz quantas tentativas restam; no 5º erro, 15 min parado. | **Toast** (login por cartão/PIN) | Mostrar "Errou 3 de 5" e, no bloqueio, o botão **"Chamar gerente"**: o PIN do gerente desbloqueia na hora. |
| 4 | Cliente pede pelo QR e fica esperando | Recusado ou aprovado não aparece para ele. | **TouchBistro** (status do pedido) | Etapas visíveis em "Minha conta": *Recebido → Conferindo com o garçom → Na cozinha → A caminho*, mais uma mensagem quando for recusado. |
| 5 | Garçom procura a mesa reservada | A mesa reservada aparece na cor própria só 1 h antes; antes disso não há indicação no mapa. | **TouchBistro** (linha do tempo de reservas) | No mapa, um pequeno relógio "20h" no canto das mesas com reserva no dia, mesmo fora da janela de 1 h. |
| 6 | Chapeiro no KDS, cliente VIP esperando | Não há como passar um pedido na frente: a ordem é a de chegada. | **Toast KDS** ("Fire"/prioridade) | Botão **"Prioridade"** no ticket (só gerente/caixa, com motivo na auditoria): o ticket sobe ao topo com borda pulsante. Campo `prioridade` em `boteco.kds.pedido` e `ORDER BY prioridade desc, criado_em`. |
| 7 | Separação com leitor de código de barras | Não há resposta sonora nem vibração; na leitura dupla a mensagem é de erro, e o funcionário acha que falhou. | **Lightspeed** (bipe de confirmação) | Bipe curto e verde para ok; bipe duplo e grave para "já lido"; vibração (`navigator.vibrate(60)`) no celular. Tratar a mesma leitura repetida em menos de 800 ms como uma só, em silêncio. |
| 8 | Fechando o caixa às 3h | O caixa não sabe se o cartão já "bateu" com a maquininha. | **Square** (fechamento guiado) | No fechamento, mostrar "Cartões: R$ 4.210 (aguardando o extrato da maquininha)". No dia seguinte, o mesmo número com ✅ (o campo `boteco_cartoes_confirmado` já existe no caixa). |

### CSS recomendado (luz baixa, toque e daltonismo)

```scss
// boteco_base/static/src/css/boteco_aparencia.scss
// 1) Alvos de toque: mínimo 48 px (Apple 44 pt / Material 48 dp). O PIN já tem 80 px (pin.css: .bt-tecla).
.o_pos_ui, .o_bt_whats, .bt-bebidas, .ck, .pt { button, .btn { min-height: 48px; min-width: 48px; } }

// 2) Status não pode depender só de cor (daltonismo): somar ícone/forma ao estado da mesa.
.table[data-boteco-status="atrasada"]::after { content: "⏱"; position: absolute; top: 2px; right: 4px; }
.table[data-boteco-status="conta"]::after    { content: "$";  position: absolute; top: 2px; right: 4px; }
.table[data-boteco-status="chamou"]::after   { content: "✋"; position: absolute; top: 2px; right: 4px; }

// 3) Contraste: no escuro, texto secundário ≥ 4,5:1 (o cinza #9ca3af sobre #111 dá ~7:1; evitar opacidade < .75).
html[data-bt-escuro] { .text-muted { color: #b8bec8 !important; } }

// 4) Movimento: quem pediu menos animação (enjoo, epilepsia) não vê a mesa pulsando.
@media (prefers-reduced-motion: reduce) { .table[data-boteco-status] { animation: none !important; } }
```

```js
// Retorno tátil e sonoro em ação crítica (aprovou, recusou, leu o lote): 1 linha por ação
navigator.vibrate?.(ok ? 40 : [60, 40, 60]);
```

---

## SEÇÃO 4 — Testes de resistência para fazer no bar (QA físico)

1. **Mesmo QR, mesmo milissegundo.** Garçom no PDV e cliente no QR mandam pedido para a mesa 5 ao mesmo tempo.
   * *Esperado:* dois pedidos separados (cada aparelho tem o seu `uuid`), as duas comandas no KDS, a conta da mesa somando os dois.
   * *O que o `anti_burst.js` faz:* só limita o toque repetido no "+" (350 ms a partir da 3ª unidade). **Não** é a proteção contra pedido duplicado; essa proteção é o `uuid` único no banco.
2. **Wi-Fi caindo no meio do envio.**
   * Com o celular no QR, desligue o roteador logo depois de tocar em "Enviar" e religue em 20 s. *Esperado:* uma comanda só no KDS e o aviso "Conexão de volta: enviando o pedido guardado" (`self_order_patch.js → botecoAoVoltarRede`).
   * Repita com 10 toques em "Enviar". *Esperado:* uma comanda.
3. **Virada do happy hour.** Coloque um chope no carrinho às 20h58 e envie às 21h01. Anote o preço mostrado e o cobrado: hoje são **diferentes** (Risco 1). Depois da correção: aviso antes de cobrar.
4. **Leitor que dispara duas vezes.** Leia a mesma etiqueta de lote duas vezes em menos de meio segundo, de dois aparelhos ao mesmo tempo. Confira a quantidade separada no `stock.move.line` (hoje pode dobrar).
5. **Turno vampiro completo.** Garçom entra às 17h, a última venda é às 02h50 e a saída às 03h10.
   * *Esperado:* as vendas das 02h50 no **dia de operação anterior**, o ponto casado com o turno "Noite" de ontem e zero hora extra se ele saiu até 01h + tolerância.
   * Repita com a virada configurada para 02h (deve quebrar) para mostrar ao dono por que a virada precisa ser depois do último fechamento.
6. **Extra: dois gerentes resolvendo a mesma quarentena** no mesmo segundo. *Esperado:* um resolve, o outro vê "já resolvido". Já é coberto pelo `FOR UPDATE` e por teste automático.

---

## SEÇÃO 5 — Ajuda: de passiva a contextual

Hoje existe: a busca (F1 / Ctrl+K, `boteco_base/static/src/ajuda/ajuda.js`), os 80+ artigos com o botão "Abrir esta tela" e o destaque do campo, as fotos das telas (`static/ajuda/*.png`, ex.: `artigo_proprio.png`, `saude_sistema.png`), Primeiros passos com a caixa na barra de cima, e o registro do que as pessoas buscam (`boteco.ajuda.busca`).

Próximo passo: a ajuda **perceber a dificuldade**, sem a pessoa pedir.

| Sinal (já disponível no sistema) | Gatilho | Ajuda proativa |
|---|---|---|
| Fechamento de conta: o caixa abriu a tela de pagamento 3 vezes na mesma mesa sem concluir, em menos de 2 min | `payment_screen_patch.js` conta aberturas por `order.uuid` | Botão pulsante "Dividir a conta? Ver como" → abre o artigo de divisão de conta com o passo destacado. |
| PIN errado 2 vezes | `pin.js` | Abaixo do teclado: "Esqueceu o PIN? O gerente troca em 10 s" (link para o artigo `cadastrar_pessoa_pin`). |
| Quarentena aberta há mais de 2 min | `aprovacoes.js` | No selo de pendências: "Pedido da mesa 7 esperando há 2 min". Uma vez por pessoa: "Como decidir?" (artigo `quarentena`). |
| Busca sem resultado na ajuda (já registrada) | `boteco.ajuda.busca` com `sem_resultado` | Semanalmente, no Painel do dono: "A equipe procurou 'trocar mesa' 9 vezes e não achou": vira o próximo artigo. |
| Primeiro uso de uma tela (por pessoa) | `res.users.boteco_tour_visto` (já existe) | Dica de 1 linha, que some no primeiro clique, em vez de um tour longo. |
| Saúde do sistema com alerta (impressora, WhatsApp, fila) | `boteco.saude._verificacoes_extras` | Faixa amarela no PDV do caixa, em linguagem simples ("Impressora da chapa sem papel ou desligada"), com o botão "Como resolver". Hoje a mensagem fica só na página `/boteco/saude`. |

Regra de ouro: **no máximo um empurrão de ajuda por tela e por turno**, sempre com "não mostrar de novo". Ajuda que atrapalha no pico vira ruído.

---

### Situação das correções (19/11/2026) — todas implementadas, 285 testes passando

| # | Correção | Onde |
|---|---|---|
| 1 | Tolerância do happy hour (padrão 5 min, em *Empresa › Boteco*): item que entrou no carrinho com preço de happy hour mantém o preço se o envio chegar até N min depois do fim. Faixa no celular/tablet nos últimos 15 min: "acaba às 21:00, envie até 21:05". | `boteco_cardapio/models/pos_order.py`, `estado_cardapio.js`, `boteco_mesa.js/xml` |
| 2 | Precisão: preço/custo 4 casas, quantidade 3 casas; preço de venda e valores em R$ continuam com 2. Fator da NF-e conferido: custo mais de 50% diferente do atual fica vermelho e só entra com "Conferi os fatores". | `boteco_base/data/precisao_data.xml`, `boteco_nfe_importacao.py` |
| 3 | Bandeja de **Pendências** no PDV: sino + aviso pequeno + contador; a janela só abre se ninguém resolver em 60 s. | `boteco_autoatendimento/static/src/pos/aprovacoes.js`, `pendencias.js/xml` |
| 4 | O cliente é avisado de "pedido confirmado" ou "não confirmado"; "Liberar celular" resolvido num tablet some dos outros. | `pos_order._boteco_finalizar_resolucao`, `self_order_patch.js`, `aprovacoes.js` |
| 5 | Leitura de lote com trava no banco (`FOR UPDATE`) e a mesma etiqueta em menos de 0,8 s contada uma vez, com bipe; produção com insumo sem saldo só fecha com o PIN do gerente (auditoria). **Defeito antigo achado e corrigido:** a reserva do próprio item era descontada do lote (9,6 kg com 5 kg pedidos separava 4,6 kg). | `stock_picking.py`, `separacao.js`, `mrp_production.py`, `producao.js/xml` |
| 6 | PIN: 5 erros bloqueiam só **naquele aparelho** (15 somando todos, contra força bruta); botão "Gerente desbloqueia aqui" na tela de PIN. | `boteco_pin_tentativa.py`, `res_users.py`, `pin_login.py`, `pin.js` |
| 7 | KDS com "⚡ Prioridade" (caixa/gerente, com motivo na auditoria); dobra de turno conta cada batida em um turno só; CMV das perdas e recebíveis no dia de operação da empresa. | `boteco_kds.py`, `kds_tela.*`, `boteco_escala/models/ponto.py`, `boteco_cmv.py`, `boteco_conciliacao` |

### Prioridade sugerida de correção
1. Aviso de mudança de preço no envio pelo QR (Risco 1).
2. Precisão de 4 casas no preço e 3 na quantidade, com migração e conferência do fator da NF-e (Risco 2).
3. Bandeja de pendências no lugar das janelas que bloqueiam o PDV (Risco 3, atrito 1).
4. Avisar o cliente sobre aprovado/recusado; fechar a janela "Liberar celular" nos outros tablets.
5. Trava na leitura de lote; estoque negativo com PIN do gerente.
6. Bloqueio de PIN por pessoa + aparelho, com contador e desbloqueio pelo gerente.
7. Prioridade no KDS; dobra de turno no ponto; dia de operação no recebível e no CMV.
