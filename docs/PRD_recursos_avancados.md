# PRD — Recursos Avançados (equivalentes ao Odoo Enterprise) e Ajuda Rápida

## Ecossistema Boteco Raiz (`Bar5` — Odoo 18 Community) — Etapas 26 a 32

| Atributo | Detalhamento |
| :--- | :--- |
| **Projeto alvo** | `Bar5` — Odoo 18 **Community** (imagem `boteco-odoo:18`), módulos `boteco_*` |
| **Origem** | Avaliação dos recursos pagos do Odoo Enterprise que trariam mais retorno a um bar com cozinha central, e pedido do dono por uma **ajuda rápida pesquisável** ("busco *cadastrar WhatsApp* e ele me mostra o caminho e a tela"). |
| **Restrição** | **Nada pode depender do Odoo Enterprise.** Os recursos pagos ficam escondidos na tela (feito em 18/11/2026); aqui eles são reconstruídos no Community, sob medida para o boteco. |
| **Governança** | Cada recurso tem chave na **Central de Recursos** (`Configuração → Sistema → Liga / desliga recursos`) e o código confere `company.boteco_recurso_ativo("<codigo>")` antes de agir — igual às Etapas 11 a 25. |
| **Modo de execução** | Interativo (human-in-the-loop): antes de cada etapa, o agente apresenta o resumo e pergunta *Implementar ativo / Implementar desativado / Pular*. Ao terminar, roda a suíte de testes e reporta. |

---

# PARTE 0 — PROTOCOLO DE EXECUÇÃO (OBRIGATÓRIO PARA O AGENTE)

1. **Uma etapa por vez.** Mostrar o resumo da etapa, as flags e perguntar: 1️⃣ ativo, 2️⃣ desativado, 3️⃣ pular.
2. **Flag antes de regra.** Toda regra nova confere a flag. Com a flag desligada, o sistema volta exatamente ao comportamento anterior.
3. **Sem Enterprise.** Não depender de `appointment`, `planning`, `quality_control`, `account_accountant`, `whatsapp`, `web_studio` nem de qualquer módulo `to_buy`.
4. **Testes e tela de verdade.** Cada etapa entrega testes automatizados e é conferida no navegador (script `scripts/dev/verificar_telas.mjs` ou equivalente), com prints anexados ao relatório.
5. **Ajuda junto.** Toda etapa que cria tela nova entrega também os **artigos de ajuda** dela (Etapa 26). Tela sem artigo não é considerada pronta.
6. **Ambiente Windows do desenvolvedor:** sem bash nativo; testes via Docker (ver `docs/MANUAL_TESTES_WINDOWS11.md`). Atualizações chegam ao servidor pela tela **Configuração → Sistema → Atualizar sistema** (`docs/atualizacao.md`).

---

# PARTE 1 — VISÃO GERAL E PRIORIDADES

| Etapa | Recurso | Equivalente pago no Odoo | Por que vale para o boteco | Prioridade |
| :--- | :--- | :--- | :--- | :--- |
| **26** | **Ajuda rápida pesquisável** (substitui o OdooBot) | Base de conhecimento / onboarding | Equipe com rotatividade alta precisa achar "como faz" sem ligar para o dono. Pré-requisito das demais. | **1 – Alta** |
| **27** | **Reserva de mesas** com lembrete e lista de espera | Appointments + reserva no PDV | Receita direta: mesa reservada não fica vazia; reduz no-show. | **2 – Alta** |
| **28** | **Conferência de cartões e Pix** (conciliação) | Contabilidade completa / conciliação bancária | É onde bar perde dinheiro sem perceber: taxa errada, repasse que não veio, estorno. | **3 – Alta** |
| **29** | **Escala de turnos + ponto pelo PIN** | Planning (+ Attendances, que é gratuito) | Custo de pessoal é o maior custo variável; escala pelo movimento previsto. | 4 – Média |
| **30** | **Checklists APPCC e manutenção preventiva** | Quality + Maintenance (Maintenance é gratuito) | Fiscalização da Vigilância Sanitária (RDC 216) e chopeira/freezer sem parar. | 5 – Média |
| **31** | **Fidelidade / cashback** | — (gratuito: `loyalty` + `pos_loyalty`) | Só configurar e integrar ao tablet e à régua de clientes. | 6 – Baixa (rápida) |
| **32** | **Desligar e esconder o OdooBot** | — | O OdooBot não ajuda o boteco e confunde a equipe; a ajuda rápida o substitui. | Junto com a 26 |

### Novas chaves da Central de Recursos

| Flag (`res.company`) | Nome na tela | Padrão |
| :--- | :--- | :--- |
| `boteco_flag_ajuda_rapida` | Ajuda rápida pesquisável (botão ? e atalho F1) | **Ligado** |
| `boteco_flag_reservas_mesas` | Reserva de mesas, lembretes e lista de espera | Desligado |
| `boteco_flag_reserva_sinal` | Cobrar sinal (Pix) em reservas de grupo grande | Desligado |
| `boteco_flag_conciliacao_cartoes` | Conferência de cartões e Pix (repasses e taxas) | Desligado |
| `boteco_flag_escala_turnos` | Escala de turnos pela previsão de movimento | Desligado |
| `boteco_flag_ponto_pin` | Ponto (entrada/saída) pelo PIN | Desligado |
| `boteco_flag_checklists_appcc` | Checklists de abertura/fechamento e APPCC | Desligado |
| `boteco_flag_manutencao_preventiva` | Manutenção preventiva (chopeira, freezers, gás) | Desligado |
| `boteco_flag_fidelidade` | Fidelidade / cashback no PDV e no tablet | Desligado |

---

# ETAPA 26 — AJUDA RÁPIDA PESQUISÁVEL ("COMO FAÇO…?")

> **🤖 CHECKPOINT:** *"Na Etapa 26 vamos criar a Ajuda rápida: o botão **?** vira uma busca. Você digita, por exemplo, **cadastrar whatsapp**, e o sistema mostra o passo a passo, o **caminho no menu**, a **foto da tela** e um botão **Abrir esta tela** que já leva até lá destacando o campo. Também desliga o OdooBot (Etapa 32). Implementar ativo, desativado ou pular?"*

## 26.1. Problema

* O botão **?** atual abre `/boteco/ajuda`, um guia fixo de uma página por perfil (`boteco_base/controllers/ajuda.py`). Não dá para **pesquisar**, não mostra **onde fica** cada coisa e não leva até a tela.
* O OdooBot (módulo `mail_bot`) está instalado, não funciona para o boteco e não é necessário.
* Depois da reorganização do menu (18/11/2026), qualquer ajuda com caminhos escritos à mão ficaria desatualizada. **O caminho precisa ser gerado a partir do menu real.**

## 26.2. Boas práticas aplicadas (pesquisa)

| Prática | Origem | Como entra no Bar5 |
| :--- | :--- | :--- |
| Ajuda **no contexto**, no momento da necessidade (tooltip, inline, passo a passo) | Userpilot, Chameleon, Whatfix | Painel lateral que abre **por cima da tela atual** e mostra primeiro a ajuda **desta tela**. |
| Combinar ajuda **"puxada"** (busca) com **"empurrada"** (dica na hora certa), sem exagerar | Chameleon (push vs. pull) | Busca sempre disponível; dicas empurradas só na 1ª vez em telas novas (já existe o `boteco_tour_visto`). |
| Começar pelos **momentos que geram dúvida repetida** | Featurebase, Userpilot | Registrar **buscas sem resultado** e **"não ajudou"** → lista para o dono/desenvolvedor escrever o próximo artigo. |
| Paleta de busca com **atalho de teclado**, **Esc fecha**, resposta instantânea | Retool, saasui.design, design systems | **F1** e **Ctrl+K** abrem a ajuda; Esc fecha; busca local em menos de 100 ms. |
| **Estado vazio útil** (sugestões) e **"sem resultado" com próximo passo** | saasui.design, Hubtel DS | Vazio = "Mais procurados pelo seu perfil"; sem resultado = sinônimos + "Pedir ajuda no WhatsApp". |
| Separar **"como fazer"** de **"ir para a tela"** e agrupar resultados | Retool, design systems | Grupos: **Como fazer** · **Telas** · **Configurações** · melhor resultado no topo. |
| A paleta **não pode ser o único caminho** | Design systems | O menu continua completo; a ajuda só encurta. |
| Medir o uso | Command.ai, Featurebase | Painel "Ajuda" na Configuração: mais buscados, sem resultado, avaliação 👍/👎 por artigo. |
| Linguagem do usuário, **sem jargão** | NN/g (rótulos) | Artigos escritos como o garçom fala; sinônimos ("zap", "celular", "telefone"). |

## 26.3. O que vamos construir

### a) Botão **?** vira **Ajuda rápida** (painel lateral)
* Ícone **?** na barra de cima (já existe) + atalhos **F1** e **Ctrl+K**.
* Abre um **painel à direita** (não troca de página; a pessoa continua vendo a tela onde estava), com:
  1. **Campo de busca** em foco ("O que você quer fazer?").
  2. **Ajuda desta tela** (artigos ligados à tela/ação aberta agora).
  3. Ao digitar, resultados em grupos: **Como fazer** (artigos) · **Telas** (menus em que a pessoa tem acesso) · **Configurações** (chaves da Central de Recursos e campos de configuração).
* Funciona igual no backend, no KDS e (versão simplificada, só artigos do perfil) no PDV.

### b) Artigo de ajuda — exemplo "cadastrar whatsapp"

Busca: `cadastrar whatsapp` (também acha por `zap`, `celular do fornecedor`, `telefone`, `lista de compras`).

> **Como cadastrar o WhatsApp de um fornecedor**
> *Para a Lista de compras enviar o pedido direto no WhatsApp dele.*
>
> **Onde fica:** `Compras e estoque › Comprar › Fornecedores` ← *gerado do menu real*
>
> 1. Abra o fornecedor (ou clique em **Novo**).
> 2. No campo **Celular**, digite o número com DDD: `(11) 98888-7777`.
> 3. Clique em **Salvar**.
>
> *[foto da tela com o campo Celular destacado]*
>
> **[ Abrir esta tela ]** → abre a lista de fornecedores e, no formulário, **pisca o campo Celular** por 3 segundos.
>
> **Relacionados:** Mandar a lista de compras pelo WhatsApp · Cadastrar o WhatsApp de um cliente (régua de clientes) · Instagram do fornecedor
>
> Isso ajudou? 👍 👎

### c) Caminho e tela **sempre certos**
* **Caminho gerado do menu** (`ir.ui.menu.complete_name`, sem o "Boteco /"): se o menu mudar de lugar, a ajuda muda sozinha. Se a pessoa não tem acesso àquele menu, o artigo diz *"Peça ao gerente"* em vez de mostrar um caminho que ela não vê.
* **Abrir esta tela:** botão que executa a **ação** do artigo (`ir.actions`) e, opcionalmente, **destaca um campo** (`destacar_campo = "mobile"`) com um contorno animado — padrão *spotlight*.
* **Foto da tela gerada automaticamente:** script `scripts/dev/gerar_capturas_ajuda.mjs` (mesma técnica de Chrome sem janela usada em 18/11/2026) abre cada artigo, destaca o campo e salva a imagem em `addons/boteco_base/static/ajuda/<codigo>.png`. Roda no desenvolvimento antes de cada versão; a foto acompanha o tema claro e a letra normal.

### d) Busca tolerante
* Ignora acentos e maiúsculas (`unaccent`), aceita erro de digitação leve (trigramas `pg_trgm` ou distância de edição no navegador) e usa **sinônimos** cadastrados por artigo.
* Índice local carregado uma vez (artigos + menus visíveis + chaves da Central), busca no navegador → resposta instantânea mesmo com Wi-Fi ruim.
* Ordenação: título > sinônimo > passos; artigos do **perfil** da pessoa e da **tela atual** primeiro.

### e) Conteúdo inicial (mínimo 40 artigos, por perfil)
| Perfil | Exemplos |
| :--- | :--- |
| Garçom | Abrir mesa e ajustar pessoas · Liberar celular do QR · Resolver pedido em conferência (quarentena) · Confirmar +18 · Transferir/juntar mesas · Dividir a conta |
| Caixa | Abrir e fechar o caixa (contagem cega) · Tirar a taxa de serviço · Sangria e reforço · CPF na nota · Portaria |
| Cozinha / chapa | Usar a fila da chapa · Desfazer um toque · Reimprimir ticket · 2º tempo da sobremesa · Registrar temperatura |
| Gerente | Cadastrar item do cardápio · Happy hour e ofertas · Lista de compras pelo WhatsApp · **Cadastrar WhatsApp do fornecedor** · Ler orçamento · Contagem de estoque · Plano de produção |
| Dono | Liga/desliga recursos · Atualizar o sistema · Cadastrar pessoa e PIN · Permissões por perfil · Instagram do fornecedor · Tema escuro e letra grande · Rateio da taxa |

Artigos ficam em **arquivo de dados versionado** (`data/boteco_ajuda_artigos.xml`, `noupdate="0"`): toda atualização do sistema leva os artigos novos. O dono pode **criar artigos próprios** pela tela (ex.: "Senha do Wi-Fi dos clientes"), que não são sobrescritos.

### f) "Não achei" e medição
* Sem resultado → mostra 3 sugestões por sinônimo e o botão **Pedir ajuda** (abre o WhatsApp do responsável configurado na empresa, com a busca já escrita).
* Cada busca sem resultado e cada 👎 vira registro em `boteco.ajuda.busca` → tela **Configuração › Acompanhamento › Ajuda: o que estão procurando**.

### g) Lacuna corrigida junto: menu **Fornecedores**
Hoje não existe menu de fornecedores dentro do Boteco. Criar `Compras e estoque › Comprar › Fornecedores` (contatos com `supplier_rank > 0`, formulário enxuto: nome, celular/WhatsApp, Instagram, CNPJ, produtos que fornece).

## 26.4. Modelo de dados

| Modelo / campo | Tipo | Observação |
| :--- | :--- | :--- |
| `boteco.ajuda.artigo` | | |
| `codigo` | Char único | ex.: `whatsapp_fornecedor` (nome da foto) |
| `titulo` / `resumo` | Char / Char | "Como cadastrar o WhatsApp de um fornecedor" |
| `sinonimos` | Char | "zap, celular, telefone, contato" |
| `passos` | Html | lista numerada curta (máx. 7 passos) |
| `menu_id` | Many2one `ir.ui.menu` | **gera o caminho** |
| `action_id` | Reference `ir.actions` | botão "Abrir esta tela" |
| `destacar_campo` | Char | nome do campo a destacar |
| `perfil_ids` | Many2many `boteco.perfil` | vazio = todos |
| `tela_xmlids` | Char | ações/modelos onde aparece como "ajuda desta tela" |
| `relacionados_ids` | Many2many self | |
| `imagem` | Image | foto gerada pelo script (ou enviada pelo dono) |
| `padrao` | Boolean | veio do sistema (não editável) × criado pelo dono |
| `uteis` / `nao_uteis` | Integer | contadores 👍/👎 |
| `boteco.ajuda.busca` | | `termo`, `usuario_id`, `perfil`, `tela`, `achou` (bool), `artigo_id`, `data` |

## 26.5. Arquivos

* `boteco_base/models/boteco_ajuda.py`, `views/boteco_ajuda_views.xml`, `data/boteco_ajuda_artigos.xml`, `security/ir.model.access.csv`.
* `boteco_base/static/src/ajuda/ajuda_painel.js|xml|scss` (painel OWL), registro como serviço com atalhos F1 / Ctrl+K e no `systray` (substitui o `abrirAjuda` de `botao_ajuda.js`).
* Rota JSON `/boteco/ajuda/indice` (artigos + menus visíveis + chaves) e `/boteco/ajuda/registrar` (busca, 👍/👎).
* `/boteco/ajuda` (página atual) passa a ser a versão "imprimir/compartilhar" do artigo.
* `scripts/dev/gerar_capturas_ajuda.mjs`.

## 26.6. Critérios de aceite
1. Buscar `cadastrar whatsapp`, `zap fornecedor` ou `celular fornecedor` traz **"Como cadastrar o WhatsApp de um fornecedor"** em 1º lugar em menos de 100 ms (índice já carregado).
2. O artigo mostra o caminho `Compras e estoque › Comprar › Fornecedores`; ao mover o menu de lugar e atualizar, o caminho exibido muda sem editar o artigo.
3. **Abrir esta tela** abre o formulário de fornecedor e destaca o campo Celular.
4. Garçom não vê artigos/caminhos de telas de dono; vê *"Peça ao gerente"* quando o artigo exigir.
5. Busca sem resultado é registrada e aparece na tela de acompanhamento.
6. F1 e Ctrl+K abrem; Esc fecha; funciona no tema escuro e com letra grande.
7. Flag `ajuda_rapida` desligada → o botão **?** volta a abrir o guia antigo.
8. Toda tela criada nas Etapas 27–31 tem ao menos 1 artigo (teste automático compara ações novas × artigos).

---

# ETAPA 32 — DESLIGAR E ESCONDER O ODOOBOT (junto com a 26)

> **🤖 CHECKPOINT:** *"Posso desligar o OdooBot para todas as pessoas e esconder a conversa com ele? Não vou desinstalar o módulo `mail_bot` (há relatos de instalação quebrada ao desinstalar)."*

* Pesquisa: o Odoo guarda o estado do bot no usuário (`res.users.odoobot_state`, valor `disabled`); desinstalar `mail_bot` é relatado como arriscado.
* **Construir:** `post_init`/migração e `create` de `res.users` gravando `odoobot_state = "disabled"`; esconder o OdooBot da lista de conversas (domínio no canal de chat com o parceiro `base.partner_root`); remover a mensagem de boas-vindas dele.
* **Aceite:** usuário novo não recebe mensagens do OdooBot; nenhuma conversa "OdooBot" aparece no ícone de mensagens; e-mails de sistema continuam saindo normalmente.

---

# ETAPA 27 — RESERVA DE MESAS, LEMBRETES E LISTA DE ESPERA

> **🤖 CHECKPOINT:** *"Na Etapa 27 vamos criar a reserva de mesas: página pública de reserva (link para Instagram/WhatsApp), mapa de reservas no salão, lembrete pelo WhatsApp, lista de espera e controle de no-show. Sinal por Pix para grupos grandes fica numa chave separada. Implementar ativo, desativado ou pular cada item?"*

## 27.1. Boas práticas (pesquisa)
* **Lembretes automáticos** 24 h e no dia são a medida mais citada contra no-show (Toast, TableCheck, The Access Group, Eat App).
* **Sinal/depósito só para grupos grandes ou horários de pico** — cobrar de todos afasta cliente (Toast, TableCheck).
* **Política clara** de tolerância e cancelamento, visível na página de reserva (Toast).
* **Lista de espera digital** que avisa o próximo quando alguém cancela (OpenTable, Sauce, Eat App).
* **Histórico do cliente com no-shows** marcados (Tablein, Okya).

## 27.2. O que vamos construir
* Modelo `boteco.reserva`: cliente (nome, celular), data/hora, pessoas, mesa(s) (`restaurant.table`, pode juntar mesas — Etapa 13), origem (link, WhatsApp, telefone, balcão), estado (`pendente`, `confirmada`, `chegou`, `no_show`, `cancelada`), observação (aniversário, cadeirinha), sinal (valor, pago).
* **Página pública** `/reservar` (sem login, com proteção contra robô e limite por IP): escolhe dia, horário (faixas configuráveis), nº de pessoas; mostra a **política de tolerância** (ex.: 15 min). Confirma na hora se houver mesa; senão oferece **lista de espera**.
* **Disponibilidade:** capacidade por faixa de horário a partir dos lugares das mesas (`seats`), tempo médio de permanência configurável (ex.: 2 h), bloqueio de mesas reservadas no **mapa do salão** (cor própria + horário).
* **Lembretes:** cron envia link `wa.me` pronto para o atendente (sem robô, como a régua de clientes) **ou**, se configurado, por um provedor de WhatsApp — lembrete D-1 e 3 h antes, com botões "Confirmo" / "Preciso cancelar" (página com token).
* **Lista de espera:** ao cancelar, o sistema sugere o 1º da lista e gera a mensagem de oferta da vaga.
* **Chegada:** garçom marca **Chegou** → abre a mesa já com o nº de pessoas da reserva (Etapa 13). Após a tolerância sem chegar → **no-show** automático e mesa liberada.
* **Sinal (flag separada):** grupos acima de N pessoas (configurável) recebem cobrança de sinal por Pix (QR estático do bar com valor e identificador; baixa manual ou pela conciliação da Etapa 28); o sinal vira crédito na conta da mesa.
* **Relatórios:** reservas por dia, taxa de no-show, clientes reincidentes (alimenta a régua de clientes da Etapa 22).

## 27.3. Critérios de aceite
1. Reserva feita pela página pública aparece no mapa do salão na mesa certa, com horário.
2. Não permite reservar além da capacidade da faixa de horário.
3. Lembrete D-1 gerado para todas as confirmadas; cliente que clica "Preciso cancelar" libera a mesa e a lista de espera é avisada.
4. 15 min após o horário sem "Chegou" → no-show registrado no histórico do cliente.
5. Flag desligada → página `/reservar` responde "Reservas indisponíveis" e o mapa não mostra reservas.

---

# ETAPA 28 — CONFERÊNCIA DE CARTÕES E PIX (CONCILIAÇÃO)

> **🤖 CHECKPOINT:** *"Na Etapa 28 vamos criar a conferência de cartões e Pix: importar o extrato da maquininha e do banco, comparar com as vendas do caixa, conferir a taxa de cada bandeira e apontar repasse atrasado ou diferença. Implementar ativo, desativado ou pular?"*

## 28.1. Boas práticas (pesquisa)
* Conciliar = conferir se o dinheiro de cada venda na maquininha **chegou na conta no valor esperado**, cruzando venda líquida × extrato de repasse (Cielo, Transfeera, TOTVS).
* Conferir **taxas contratadas × aplicadas**, **prazos de repasse**, **estornos/cancelamentos**, **antecipação** e parcelado (Omie, Contábeis).
* Divergências comuns: digitação, atraso de compensação, taxa não prevista, fraude; pequenas diferenças diárias somam muito no ano (Auditto, Mercado Pago).
* Fazer **pelo menos semanalmente**, transação por transação quando houver diferença (Monitor Mercantil, Contábeis).

## 28.2. O que vamos construir
* **Cadastro de adquirentes** (`boteco.adquirente`): nome (Stone, Cielo, Rede, PagSeguro, Mercado Pago…), forma de pagamento do PDV ligada, **tabela de taxas contratadas** por modalidade (débito, crédito à vista, parcelado por nº de parcelas, Pix) e **prazo de repasse** (D+1, D+30…).
* **Previsão de recebíveis:** cada pagamento do PDV gera um **recebível previsto** (valor bruto, taxa esperada, líquido esperado, data prevista) — `boteco.recebivel`.
* **Importação do extrato da maquininha:** CSV/XLSX padrão de cada adquirente (leitor configurável por colunas, como o layout fiscal da Etapa 9) e **extrato bancário OFX** (Pix e repasses).
* **Casamento automático** recebível × extrato por valor, data, NSU/autorização e bandeira; o que sobra vai para a fila **"Conferir"**.
* **Alertas:** taxa aplicada acima da contratada; repasse atrasado além do prazo; venda no caixa sem registro na maquininha (e vice-versa); estorno/chargeback.
* **Painel do dono:** card "Cartões e Pix" com *a receber nos próximos 30 dias*, *diferenças da semana* e *quanto se pagou de taxa no mês por adquirente* (base para negociar taxa).
* **Fechamento de caixa** (Etapa 2) passa a mostrar, no dia seguinte, quanto do caixa já foi confirmado pela maquininha.

## 28.3. Critérios de aceite
1. Extrato de teste da maquininha casa 100% das vendas iguais e aponta as que diferem.
2. Taxa cobrada 0,3 p.p. acima da contratada gera alerta com o valor perdido.
3. Repasse não recebido até a data prevista + 1 dia útil aparece como atrasado.
4. Pix pago na conta sem venda correspondente aparece na fila "Conferir".
5. Flag desligada → nenhum recebível é gerado e o card some do painel.

---

# ETAPA 29 — ESCALA DE TURNOS PELO MOVIMENTO E PONTO PELO PIN

> **🤖 CHECKPOINT:** *"Na Etapa 29 vamos criar a escala de turnos (sugerida pela previsão de movimento) e o ponto pelo PIN. São duas chaves separadas. Implementar ativo, desativado ou pular cada uma?"*

## 29.1. Boas práticas (pesquisa)
* Escala ligada à **previsão de vendas** e à meta de **custo de pessoal sobre faturamento**, vista **antes** de publicar (Workforce.com, Fourth).
* **Integração com o PDV** para ver custo de pessoal × vendas quase em tempo real (Workforce.com).
* **Troca de turno** pelo app com **aprovação do gerente** e regras (não deixar a sexta sem ninguém) (Connecteam, Shyft).
* Alertas antes de publicar: horas extras, intervalo, folga semanal (Workforce.com).
* Ponto integrado reduz conferência manual de folha (Fourth).

## 29.2. O que vamos construir
* **Previsão de movimento por turno** a partir do histórico (clientes e faturamento por dia da semana/hora — dados que o painel já calcula), ajustável (feriado, jogo, show com couvert).
* **Regra de cobertura**: clientes por garçom, pratos por chapeiro etc. (configurável por perfil) → **sugestão de quantas pessoas por turno**.
* **Escala da semana** (`boteco.escala.turno`): grade arrastar-e-soltar por pessoa/perfil; mostra custo previsto e **% do faturamento previsto**; alertas (horas acima do limite, sem folga na semana, turno descoberto).
* **Publicar** → cada pessoa vê a própria escala na **Minha tela** e recebe link pelo WhatsApp; **troca de turno** pedida pela pessoa e aprovada pelo gerente.
* **Ponto pelo PIN (flag própria):** usa o módulo **gratuito `hr_attendance`**; entrada/saída digitando o PIN na tela de login por PIN (que já existe), opcionalmente só na rede do bar (Etapa 4 já tem o controle de rede). Relatório **escalado × trabalhado** e exportação para a folha/contador (CSV).

## 29.3. Critérios de aceite
1. Com 4 semanas de histórico, a sugestão de sexta à noite mostra mais garçons que a de terça.
2. Escala com alguém sem folga na semana não publica sem confirmação.
3. Troca de turno só vale depois da aprovação.
4. Ponto pelo PIN fora da rede do bar é recusado (quando a regra estiver ligada).
5. Relatório escalado × trabalhado mostra atrasos e horas extras por pessoa.

---

# ETAPA 30 — CHECKLISTS APPCC E MANUTENÇÃO PREVENTIVA

> **🤖 CHECKPOINT:** *"Na Etapa 30 vamos criar checklists (abertura, fechamento, APPCC) com foto e assinatura por PIN, e a manutenção preventiva da chopeira, freezers e gás. Implementar ativo, desativado ou pular cada um?"*

## 30.1. Boas práticas e norma (pesquisa)
* A **RDC 216/2004 (Anvisa)** exige Boas Práticas em serviços de alimentação, com **Manual de Boas Práticas** e **POPs** (Procedimentos Operacionais Padronizados); checklists de verificação baseados nela costumam ter ~90 itens em blocos (edificação, higiene, controle de pragas, manipuladores, armazenamento…).
* Registros de **temperatura** e **limpeza** são a prova na fiscalização — a cozinha central já registra temperaturas (Etapa 7).
* Manutenção preventiva: o módulo `maintenance` do Odoo é **gratuito** e pode ser a base (equipamentos, planos periódicos).

## 30.2. O que vamos construir
* **Modelos de checklist** (`boteco.checklist.modelo`): itens com tipo (sim/não, número com faixa — ex.: temperatura 0–5 °C —, foto obrigatória, texto), setor, perfil responsável, frequência (abertura, fechamento, diária, semanal) e **item crítico** (se falhar, avisa o gerente na hora).
* **Modelos prontos** para importar: *Abertura do salão*, *Fechamento da cozinha*, *Recebimento de mercadoria* (temperatura e validade), *Higienização da chopeira*, *Controle de pragas (registro da empresa contratada)*, base RDC 216.
* **Execução pelo celular/tablet** (tela de toque, como a contagem de estoque): marca, fotografa, assina com o **PIN**. Pendências do dia aparecem na **Minha tela** de cada perfil.
* **Não conformidade** → tarefa com responsável e prazo; reaparece até ser resolvida.
* **Relatório para a fiscalização:** PDF por período com todos os registros, fotos e quem assinou (junto com o relatório de temperaturas já existente).
* **Manutenção preventiva** (sobre `maintenance` gratuito): equipamentos (chopeira, freezers/câmaras — já cadastrados na Etapa 7 —, coifa, gás, filtros), plano periódico (ex.: limpeza da chopeira a cada 7 dias, troca do filtro de água a cada 6 meses, recarga/teste de extintor), aviso antes de vencer e histórico com custo.

## 30.3. Critérios de aceite
1. Checklist de abertura não finalizado até a hora limite aparece em vermelho para o gerente.
2. Temperatura fora da faixa num item crítico gera alerta imediato e não conformidade.
3. PDF do mês reúne checklists, fotos e assinaturas por PIN.
4. Limpeza da chopeira vencida aparece na Minha tela do gerente e no painel do dono.

---

# ETAPA 31 — FIDELIDADE / CASHBACK (MÓDULOS GRATUITOS)

> **🤖 CHECKPOINT:** *"Na Etapa 31 vamos instalar e configurar a fidelidade gratuita do Odoo (`loyalty` + `pos_loyalty`) para o boteco: cartão fidelidade (ex.: a cada 10 chopes, 1 grátis) ou cashback, visível no tablet e na régua de clientes. Implementar ativo, desativado ou pular?"*

* Instalar `loyalty` e `pos_loyalty` (Community) e criar **programas modelo** desativados: *10 chopes = 1 grátis*, *cashback de 5% para usar na próxima visita*, *cupom de aniversário* (liga com a régua de aniversariantes da Etapa 22).
* Identificação do cliente pelo **celular** (sem cartão físico); no **tablet**, "Minha conta" mostra os pontos/cashback da mesa.
* Respeitar as regras do boteco: não acumular com happy hour/oferta relâmpago (configurável) e não valer em consumo de funcionário.
* **Aceite:** 10º chope do mesmo cliente sai com desconto de 100% automaticamente; saldo aparece no tablet; flag desligada não oferece programas no PDV.

---

# PARTE 2 — ITENS DESCARTADOS (E POR QUÊ)

| Recurso pago | Decisão | Motivo |
| :--- | :--- | :--- |
| Leitor de código de barras (Barcode) | Não desenvolver | Contagem pelo celular e QR nas transferências já cobrem o uso do boteco. |
| KDS do Odoo (Preparation Display) | Não desenvolver | O KDS próprio (Etapas 5, 15 e 21) é mais completo. |
| WhatsApp oficial (Enterprise) | Não desenvolver agora | Links `wa.me` resolvem sem custo; integração com provedor fica para quando houver contrato. |
| Studio, Sign, Documents | Não desenvolver | Não resolvem dor do boteco hoje. |

---

# PARTE 3 — ORDEM SUGERIDA E ESTIMATIVA

| Ordem | Etapa | Esforço estimado |
| :--- | :--- | :--- |
| 1 | 26 + 32 Ajuda rápida e OdooBot | Médio (painel, busca, 40 artigos, script de fotos) |
| 2 | 31 Fidelidade | Pequeno (configuração + integração) |
| 3 | 27 Reservas | Grande |
| 4 | 28 Conferência de cartões e Pix | Grande (leitores de extrato por adquirente) |
| 5 | 30 Checklists e manutenção | Médio |
| 6 | 29 Escala e ponto | Grande |

---

# PARTE 4 — REFERÊNCIAS CONSULTADAS

**Ajuda no sistema e busca:**
[Userpilot – contextual help](https://userpilot.com/blog/contextual-help/) ·
[Userpilot – in-app guidance](https://userpilot.com/blog/in-app-guidance-saas/) ·
[Chameleon – push vs. pull help](https://chameleon.io/blog/delivering-help-ux) ·
[Featurebase – in-app support](https://www.featurebase.app/blog/in-app-customer-support) ·
[Whatfix – in-app support](https://whatfix.com/blog/product-support/) ·
[Docsie – context-sensitive help](https://docsie.io/blog/es/articles/10-key-factors-to-consider-when-building-context-sensitive-help-in-app-guidance) ·
[Trevor Calabro – onboarding & in-app help](https://trevorcalabro.substack.com/p/onboarding-and-in-app-help-strategy) ·
[SaaS UI – command palette patterns](https://www.saasui.design/blog/saas-search-command-palette-ux-patterns) ·
[Retool – designing the command palette](https://tryretool.com/blog/designing-the-command-palette) ·
[Command.ai – command palette](https://command.ai/blog/command-palette-past-present-and-future) ·
[Hubtel Design System – command palette](https://ux.hubtel.com/design-system/components/command-palette/) ·
[Health Metrics DS – command](https://designsystem.healthmetrics.com/components/overlays/command)

**Reservas:**
[Toast – reservations and waitlists](https://pos.toasttab.com/au/blog/on-the-line/best-practices-for-managing-reservations-and-waitlists-for-your-restaurant) ·
[Toast – reservation policies](https://pos.toasttab.com/zh-us/blog/on-the-line/reservation-policies) ·
[TableCheck – no-shows](https://www.tablecheck.com/en/blog/strategies-minimize-restaurant-no-shows/) ·
[The Access Group – no-shows](https://www.theaccessgroup.com/en-gb/blog/hos-8-ways-to-reduce-no-shows-in-your-restaurant/) ·
[Eat App – no-shows](https://restaurant.eatapp.co/blog/restaurant-no-shows) ·
[Sauce – reservation systems](https://www.getsauce.com/post/mastering-restaurant-reservations-systems) ·
[Tablein – no-shows](https://tablein.com/blog/how-to-deal-with-restaurant-no-shows) ·
[Okya – deposits and reminders](https://okya.co/blog/fixing-restaurant-no-shows-deposits-reminders-smart-reservations)

**Conciliação de cartões:**
[Cielo – conciliação financeira de cartões](https://blog.cielo.com.br/financas/conciliacao-financeira-de-cartoes/?amp=1) ·
[Transfeera – conciliação de cartões](https://transfeera.com/blog/conciliacao-de-cartoes/) ·
[TOTVS – conciliação de cartões](https://www.totvs.com/blog/gestao-financeira/conciliacao-de-cartoes/) ·
[Omie – conciliação de recebíveis](https://www.omie.com.br/blog/conciliacao-de-recebiveis-garanta-entrada-financeira/) ·
[Contábeis – passo a passo](https://www.contabeis.com.br/artigos/5336/aprenda-o-passo-a-passo-para-fazer-a-conciliacao-de-cartoes/) ·
[Auditto – conciliação de cartão](https://auditto.com.br/como-a-conciliacao-de-cartao-pode-melhorar-seu-negocio) ·
[Mercado Pago – conciliação financeira](https://www.mercadopago.com.br/blog/conciliacao-financeira) ·
[Monitor Mercantil – perdas com cartão](https://monitormercantil.com.br/gest-o-financeira-eficiente-reduz-perdas-nas-vendas-com-cart-o/)

**Escala de turnos:**
[Workforce.com – WFM for restaurants](https://workforce.com/buyers-guides/wfm-restaurants) ·
[Workforce.com – scheduling](https://workforce.com/buyers-guides/restaurants-hospitality-scheduling) ·
[Fourth – labor forecasting](https://www.fourth.com/labor-forecasting) ·
[Connecteam – restaurant scheduling](https://connecteam.com/restaurant-scheduling-software) ·
[Begin – scheduling guide](https://heybegin.com/blog/restaurant-scheduling-software)

**APPCC / RDC 216:**
[RDC 216/2004 – Prefeitura do Rio](https://vigilanciasanitaria.prefeitura.rio/wp-content/uploads/sites/84/2023/05/RESOLUcaORDCN216ANVISA.pdf) ·
[Cartilha de Boas Práticas – Rio](https://vigilanciasanitaria.prefeitura.rio/wp-content/uploads/sites/84/2023/06/CartilhaBoasPraticas_Livreto.pdf) ·
[Legisweb – RDC 216](https://www.legisweb.com.br/legislacao/?id=100899)

**OdooBot:**
[Fórum Odoo – desligar o OdooBot](https://www.odoo.com/forum/help-1/odoo-12-get-rid-of-that-odoo-bot-144178)
