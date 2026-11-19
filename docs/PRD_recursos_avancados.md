# PRD — Recursos Avançados, Ajuda Rápida, Primeiros Passos e Simplificação

## Ecossistema Boteco Raiz (`Bar5` — Odoo 18 Community) — Etapas 26 a 36

| Atributo | Detalhamento |
| :--- | :--- |
| **Projeto alvo** | `Bar5` — Odoo 18 **Community** (imagem `boteco-odoo:18`), módulos `boteco_*` |
| **Origem** | (1) Avaliação dos recursos pagos do Odoo Enterprise que trariam mais retorno a um bar com cozinha central; (2) pedido do dono por uma **ajuda rápida pesquisável** ("busco *cadastrar WhatsApp* e ele me mostra o caminho e a tela"); (3) **manual passo a passo na primeira entrada** ("vamos primeiro cadastrar a empresa…"); (4) PRDs incorporados em 18/11/2026: **Simplificação do PDV e Automação de Cotações** e **QR Code Expresso de Bebidas**. |
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
| **33** | **Assistente de primeira configuração (Primeiros passos)** | — (o Odoo só tem um painel de onboarding genérico) | Leva o dono da instalação até uma venda de teste, sem esquecer nada. | **1 – Alta** |
| **34** | **Simplificação do PDV e isolamento por perfil** | — | Menos botões e menus para garçom/caixa = atendimento mais rápido. | **2 – Alta** |
| **35** | **Cotações automáticas: WhatsApp e coletor de sites/Instagram** | — | Preço de fornecedor entra sozinho; robôs fora do servidor do PDV. | 4 – Média |
| **36** | **QR Code expresso de bebidas** | — | Repetir a rodada com 1 toque aumenta o giro de bebida, que é a maior margem. | **2 – Alta** |

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
| `boteco_flag_assistente_implantacao` | Primeiros passos (assistente de configuração) | **Ligado** |
| `boteco_flag_vendas_b2b` | Venda a bares (B2B): menus, card e pedidos recorrentes | Desligado |
| `boteco_flag_cotacoes_whatsapp` | Receber cotações dos fornecedores pelo WhatsApp | Desligado |
| `boteco_flag_coletor_ofertas` | Coletor externo de ofertas (sites e Instagram) | Desligado |
| `boteco_flag_qr_bebidas` | QR Code expresso de bebidas (2º QR por mesa, sempre disponível) | **Ligado** |

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

# ETAPA 33 — ASSISTENTE DE PRIMEIRA CONFIGURAÇÃO ("PRIMEIROS PASSOS")

> **🤖 CHECKPOINT:** *"Na Etapa 33 vamos criar o assistente de primeira configuração: na primeira vez que o dono entra, o sistema abre a tela **Primeiros passos** — vamos cadastrar a empresa, depois a equipe, o salão, o cardápio, o caixa — até fazer uma venda de teste e abrir a casa. Implementar ativo, desativado ou pular?"*

## 33.1. Problema
* Hoje a configuração inicial é feita pelo instalador (`instalar.sh` → `scripts/configurar_empresa.py`), que cria empresa, armazéns, PDV, formas de pagamento e 20 mesas com valores padrão. Depois disso **o dono não sabe o que falta** para o boteco funcionar de verdade (cardápio, impressoras, equipe com PIN, taxa, fornecedores…).
* As telas existem, mas espalhadas por 7 menus; não há ordem nem indicação do que é obrigatório.

## 33.2. Boas práticas aplicadas (pesquisa)
| Prática | Origem | Como entra no Bar5 |
| :--- | :--- | :--- |
| **Assistente (wizard) só para o que bloqueia**; o resto vira **lista de primeiros passos persistente**, feita ao longo dos dias | Kompassify (onboarding wizard guide) | Assistente curto só com a **empresa** (o mínimo para o sistema funcionar). Todo o resto fica na tela **Primeiros passos**, que dá para fazer aos poucos. |
| Wizards servem para **processos raros e para quem não conhece o assunto** — exatamente a configuração inicial | NN/g (Wizards), PatternFly | Um passo por tela, em ordem, com "Voltar" e "Próximo". |
| **Trabalhar com dados reais, não com tutorial de mentira** | Microsoft (User Assistance guidelines) | Cada passo abre a **tela de verdade** (cadastro de pessoas, mesas, cardápio) já filtrada; o que for preenchido fica valendo. |
| Lista curta de **3 a 5 marcos com resultado**, não uma dúzia de tarefas soltas | saasui.design | Os passos são agrupados em **4 fases**; dentro delas, poucos itens obrigatórios. |
| Lista que **some quando termina** e **não reaparece** à força | saasui.design | Ao concluir, vira só um selo "Implantação concluída" no Início; pode ser reaberta pelo menu. |
| Foco no **primeiro resultado** (time-to-value) | Supademo, Appcues | A fase 4 termina com uma **venda de teste de ponta a ponta** no modo treinamento — o dono vê o boteco funcionando. |
| Usuário **não lê texto longo** dentro de wizard | LogRocket, NN/g | Cada passo: 1 frase de explicação + o que preencher + "Ver ajuda" (artigo da Etapa 26). |
| Implantação de PDV de restaurante: **cardápio → hardware (impressoras/KDS) → mesas → equipe e perfis → teste e treino por função** | Lightspeed, SkyTab/Shift4, Lavu, Platter | Mesma lógica nas fases; treino por perfil com o tour de 3 passos que já existe. |

## 33.3. O que vamos construir

### a) Assistente curto (só o que bloqueia) — primeira entrada do dono
Tela cheia, 3 telas, com barra de progresso:
1. **Sua empresa:** nome fantasia, razão social, CNPJ, endereço, telefone/WhatsApp, logo (vai no ticket e no tablet). Já vem preenchido com o que o instalador recebeu (`EMPRESA_NOME`, `EMPRESA_CNPJ`, `EMPRESA_CIDADE`).
2. **Como é o seu negócio:** só o bar · bar + cozinha central (mesmo CNPJ ou outro) — liga/desliga os recursos ligados a isso na Central de Recursos.
3. **Pronto para começar:** mostra as fases da lista de primeiros passos e leva para ela.

### b) Tela **Primeiros passos** (lista persistente, em `Início › Primeiros passos`)
Abre como **tela inicial do dono** até a implantação terminar; barra de progresso no topo ("Faltam 4 passos para abrir a casa").

| Fase | Passo | Obrigatório | Concluído quando… (verificação automática) |
| :--- | :--- | :--- | :--- |
| **1. Sua empresa** | Dados da empresa e logo | ✅ | CNPJ e endereço preenchidos |
| | Rede do Wi-Fi dos clientes e da equipe | — | redes preenchidas (Etapa 4) |
| **2. Sua equipe** | Cadastrar as pessoas com perfil e PIN | ✅ | ≥ 1 gerente/caixa e ≥ 1 garçom com PIN |
| | Revisar permissões por perfil | — | aberto pelo menos uma vez |
| **3. Seu salão e cardápio** | Plantas e mesas (lugares de cada mesa) | ✅ | ≥ 1 planta com mesas e lugares |
| | Setores e impressoras — **imprimir teste** | ✅ | cada setor com impressora que imprimiu o teste |
| | Cardápio: categorias e itens (ou **importar planilha**) | ✅ | ≥ 10 itens à venda com setor |
| | Classificar consumo e utensílios (Etapa 12) | — | itens com tipo de consumo |
| | Dados fiscais dos itens | — | nenhum item em "Itens sem dados fiscais" |
| | Formas de pagamento, taxa de serviço e couvert | ✅ | ≥ 1 forma além de dinheiro |
| | Imprimir os **QR Codes das mesas** | — | relatório gerado |
| **4. Testar e abrir** | **Venda de teste** no modo treinamento: abrir caixa → pedido na mesa → sai no bar e na chapa → pagar → fechar caixa | ✅ | venda de teste concluída (registro do modo treinamento) |
| | Treinar a equipe por função (tour de 3 passos de cada perfil) | — | cada pessoa viu o tour (`boteco_tour_visto`) |
| | **Abrir a casa** 🎉 | ✅ | botão final: confirma e encerra a implantação |
| **Depois de abrir** | Fornecedores (WhatsApp/Instagram) e lista de compras | — | ≥ 1 fornecedor com celular |
| | Fichas técnicas dos itens principais e estoque inicial (contagem) | — | ≥ 1 ficha técnica; 1 contagem aprovada |
| | Cozinha central: receitas, capacidade e freezers | — | (só se tiver cozinha central) |
| | Revisar a Central de Recursos | — | aberta pelo menos uma vez |
| | Configurar backup na nuvem | — | último backup na nuvem há menos de 48 h (página Saúde) |

Cada passo tem: **o que é e por que importa** (1 frase), botão **Fazer agora** (abre a tela real), **Ver ajuda** (artigo da Etapa 26), **Pular por enquanto** (passos não obrigatórios) e marca ✅ sozinho quando a verificação passa — não depende de a pessoa lembrar de marcar.

### c) Regras
* Só o **dono** vê o assistente e a lista; os demais perfis continuam com o tour curto de 3 passos que já existe.
* Pode sair a qualquer momento e **continuar de onde parou**; o progresso fica na empresa.
* Instalação que **já está em uso** (como o banco atual): na atualização, as verificações rodam e marcam como concluído tudo o que já existe — o dono só vê o que realmente falta, e o assistente da primeira entrada não abre.
* "Abrir a casa" com passo obrigatório pendente pede confirmação explícita (pode abrir, mas fica registrado na auditoria).

### d) Modelo de dados e arquivos
* `boteco.implantacao.passo` (dados versionados): `codigo`, `fase`, `sequencia`, `titulo`, `explicacao`, `obrigatorio`, `action_id`, `artigo_ajuda_id`, `metodo_verificacao` (nome do método Python que devolve True/False), `so_com_cozinha_central`.
* `boteco.implantacao.estado` (por empresa): passo, `situacao` (`pendente`, `feito`, `pulado`), quem/quando.
* `res.company.boteco_implantacao_concluida` (Boolean) e `boteco_implantacao_concluida_em`.
* `boteco_base/static/src/implantacao/` (assistente e lista em OWL), `views/boteco_implantacao_views.xml`, `data/boteco_implantacao_passos.xml`.
* O `configurar_empresa.py` continua: ele prepara o terreno; o assistente confirma e completa com o dono.

## 33.4. Critérios de aceite
1. Banco novo: na primeira entrada do dono abre o assistente (3 telas); depois cai na lista **Primeiros passos**.
2. Cadastrar 10 itens com setor marca o passo "Cardápio" como feito, sem clicar em "marcar como feito".
3. Imprimir o teste numa impressora marca o passo "Impressoras".
4. A venda de teste é feita no **modo treinamento** e não aparece no faturamento real.
5. Banco já em uso (o atual): após atualizar, a lista mostra concluídos os passos já atendidos e o assistente não abre.
6. Garçom/caixa nunca veem o assistente nem a lista.
7. Flag `assistente_implantacao` desligada: a lista some do Início e nada é exibido.

---

# ETAPA 34 — SIMPLIFICAÇÃO DO PDV E ISOLAMENTO POR PERFIL

> **🤖 CHECKPOINT:** *"Na Etapa 34 vamos enxugar o que cada perfil vê: esconder a Venda a bares (B2B) e o Fiscal de quem não usa, impedir a instalação de frete/Correios, deixar a Cozinha central só para quem produz e tirar do PDV os botões que garçom e caixa não usam. Implementar ativo, desativado ou pular cada item?"*

*Origem: PRD "Simplificação do PDV e Automação de Cotações de Fornecedores", seção 2 (incorporado em 18/11/2026).*

## 34.1. Objetivo
A interface do salão/caixa tem funções demais, o que confunde e atrasa o atendimento. Esta etapa é sobretudo **configuração e permissões** (pouco código novo).

## 34.2. Venda a bares (B2B) — esconder, **não desinstalar**
* ⚠️ **Divergência com o PRD de origem**, que pedia desinstalar o `boteco_b2b`: o **Painel do dono** (`boteco_painel`) e o **Fiscal** (`boteco_fiscal_export`) **dependem** dele — desinstalar removeria os dois junto, com dados.
* **Construir:** chave `boteco_flag_vendas_b2b` (padrão **desligado**). Desligada: menus de "Venda a bares (B2B)" e o card de metas B2B do painel somem; pedidos recorrentes não são gerados; os dados ficam guardados. Ligar de novo traz tudo de volta.
* Se no futuro o B2B for mesmo abandonado, a desinstalação exige antes separar as dependências (tarefa própria).

## 34.3. Fiscal — só Contabilidade e dono
* Criar o **perfil "Contador"** (grupo `boteco_base.group_contador`): vê só `Finanças › Fiscal` e `Finanças › Relatórios`, sem PDV, salão ou estoque.
* Telas de exportação/retorno, lotes e layouts do arquivo fiscal: visíveis **só para Contador e Dono** (hoje: só dono). Gerente de salão continua sem acesso.

## 34.4. Frete e Correios — impedir
* Os módulos de frete (`delivery`, `stock_delivery`) **não estão instalados** no banco atual. Esconder nas Configurações as opções que os instalariam ("Métodos de entrega", "Sistema de gerenciamento de despacho"), do mesmo jeito que as opções pagas foram escondidas, e bloqueá-los na lista de Aplicativos.
* O **delivery próprio** continua (está no `boteco_pos`: bairros, entregas e acerto de motoboys — Etapa 22). *Obs.: o PRD de origem cita `boteco_delivery`; esse módulo não existe — o recurso fica no `boteco_pos`.*

## 34.5. Cozinha central só para quem produz
* Hoje `Produção › Cozinha central` aparece para **Cozinheiro e Gerente**. Passa a aparecer **só para o perfil Cozinheiro (gerente de cozinha/produção) e o Dono**. Gerente de salão perde o acesso a: plano de produção, ordens de produção, separação, lotes e rastreio.
* **Garçom/caixa veem só o produto final.** Padrão de cadastro (com artigo de ajuda e conferência automática):
  * **"Bolinho de bacalhau congelado (para levar)"** → produto **sem setor**: a venda **só baixa o estoque** do congelado.
  * **"Porção de bolinho de bacalhau (frita)"** → produto com **setor Chapa** e **ficha técnica tipo kit** que consome o congelado: a venda **baixa o estoque do congelado e manda para o KDS** do chapeiro.
  * Isso já funciona com o que existe (`pos_mrp` + setor do produto, Etapas 5 e 6). A etapa entrega: modelo pronto nos dados de exemplo, aviso no cadastro quando um item "frito/preparado" não tem setor ou ficha, e teste automático dos dois caminhos.

## 34.6. PDV enxuto por perfil
* Levantar os botões do PDV (barra de controle, tela de pagamento, ações da conta) e definir, **por perfil**, quais aparecem. Padrão sugerido: **garçom** — abrir mesa, pedir, enviar, dividir, transferir, pedir conta; **caixa** — + receber, CPF na nota, sangria/reforço, fechar caixa; o resto (lista de preços, reembolso, nota de crédito, cliente avançado…) só para gerente.
* Configurável na tela **Permissões por perfil** (Etapa 1), não no código.

## 34.7. Critérios de aceite
1. Com a chave B2B desligada, nenhum menu, card ou cron de B2B aparece/roda; ligando, tudo volta com os dados.
2. Usuário Contador vê só Finanças (Fiscal e Relatórios).
3. Não é possível instalar frete/Correios pelas Configurações nem pelos Aplicativos.
4. Gerente de salão não vê `Produção › Cozinha central`; Cozinheiro vê.
5. Venda de "bolinho congelado" só baixa estoque; venda de "porção frita" baixa o congelado **e** cria ticket na chapa.
6. Garçom não vê botões de reembolso/lista de preços no PDV.

---

# ETAPA 35 — AUTOMAÇÃO DE COTAÇÕES: WHATSAPP E COLETOR DE SITES/INSTAGRAM

> **🤖 CHECKPOINT:** *"Na Etapa 35 vamos receber as tabelas de preço que os fornecedores mandam no WhatsApp direto no sistema e criar um coletor externo que lê sites e Instagram dos fornecedores, sem pesar no PDV. Implementar ativo, desativado ou pular cada item?"*

*Origem: PRD "Simplificação do PDV e Automação de Cotações de Fornecedores", seções 3 e 4 (incorporado em 18/11/2026).*

## 35.1. O que já existe (Etapa 18) e o que muda
| Já existe | Muda nesta etapa |
| :--- | :--- |
| Leitor de orçamento por **PDF, foto ou texto colado** (`boteco.importar.orcamento`), com parser próprio e leitura de foto por IA de visão | Passa a receber **automaticamente** pelo WhatsApp, sem ninguém colar nada |
| Leitura do **Instagram** dentro do Odoo (cron 8h e 14h, `instaloader`) | ⚠️ Migra para o **coletor externo** (regra do PRD de origem: robôs não rodam no servidor do PDV) e passa a rodar **1 vez por dia** (decisão do dono, 18/11/2026), às **8:00** (horário configurável). |
| **Radar de preços** (`boteco.historico.preco`), economia nos congelados e fornecedor mais barato na lista de compras | Recebe as novas origens (`whatsapp`, `site`) e mostra tudo "mastigado" na **Lista de compras** |

## 35.2. Leitor de cotações pelo WhatsApp

### a) Conectar o WhatsApp lendo um QR Code (decisão do dono, 18/11/2026)
Funciona como o **WhatsApp Web**: o sistema mostra um QR Code e o dono adiciona o Bar5 como **dispositivo conectado** no próprio WhatsApp. Não precisa de número novo nem da API oficial paga.

* **Serviço de conexão:** contêiner **Evolution API** (código aberto, baseado em Baileys — já citado no PRD Master) no `docker-compose`, perfil opcional, só na rede interna (sem porta exposta para a internet); o Odoo conversa com ele por token.
* **Tela `Configuração › Sistema › WhatsApp (conectar)`** (só dono):
  1. Botão **Conectar WhatsApp** → o Odoo pede ao Evolution API uma sessão e **mostra o QR Code** na tela (atualiza sozinho quando expira, a cada ~40 s).
  2. Instruções ao lado, com imagens: *no celular, abra o WhatsApp › ⋮ (ou Configurações) › **Dispositivos conectados** › **Conectar um dispositivo** › aponte para este QR Code*.
  3. Conectou → mostra **"Conectado: (11) 9xxxx-xxxx"**, desde quando, e o botão **Desconectar**.
  4. Situação sempre visível (conectado / desconectado / celular sem internet); se cair, aviso no Painel do dono e na página **Saúde do sistema**, com botão **Conectar de novo** (novo QR).
* **O que ele lê:** só as mensagens recebidas de números **cadastrados como fornecedor** (abaixo). Mensagens de clientes, família e grupos são **descartadas na hora, sem gravar** — o sistema nunca mostra nem guarda conversas que não sejam de fornecedor. Nada é enviado pelo sistema sem o dono pedir.
* **Riscos (registrar no checkpoint):** conexão não oficial pode ser desconectada ou, em casos raros, gerar bloqueio do número pelo WhatsApp; se o celular ficar muitos dias sem internet, a sessão cai e precisa ler o QR de novo. **Decidido (18/11/2026): conectar o WhatsApp do bar**, não o número pessoal do dono — se a conexão cair ou for bloqueada, o número pessoal não é afetado.

### b) Leitura das cotações
* **Gatilho:** mensagem recebida de um número **cadastrado como celular de fornecedor** (`res.partner`, número normalizado com DDI). Número desconhecido é ignorado sem gravar o conteúdo (só aparece "1 número não cadastrado mandou mensagem com preços", se o parser achar preço, para o dono cadastrar o fornecedor se quiser).
* **Processamento:** texto → parser de linhas (o mesmo da Etapa 18); PDF → texto do PDF; foto → leitura por IA de visão (chave configurada pelo dono). Itens casados com o insumo pelo **de-para do fornecedor** (que aprende sozinho).
* **Ação final:** grava em `boteco.historico.preco` (origem `whatsapp`) e atualiza o preço do fornecedor no produto (`product.supplierinfo`). Itens que não casaram ficam numa fila **"Cotações para revisar"**, com 1 toque para ligar ao insumo.
* **Endpoint:** `POST /boteco/compras/whatsapp/<token>` (webhook que o Evolution API chama a cada mensagem recebida) com resposta imediata e processamento **em fila** (job assíncrono), para não segurar o servidor.

## 35.3. Coletor de sites e Instagram (serviço externo)
* **Serviço separado** `boteco-coletor` (contêiner próprio no `docker-compose`, perfil opcional), em Python com **Playwright** (sites com JavaScript) e a leitura de Instagram que hoje está no Odoo.
* **Fontes:** por fornecedor — URL do site/encarte, perfil do Instagram e **palavras-chave** (ex.: "Cerveja 600ml", "Oferta", "R$"). Cadastradas no Odoo; o coletor busca a lista pela API.
* **Agenda:** Instagram **1 vez por dia** (padrão 8:00); sites **2 vezes por semana** (padrão seg e qui, 8:00). Horários configuráveis na tela.
* **Envio:** `POST /boteco/compras/api/cotacoes` com os itens extraídos (produto, preço, unidade, fonte, link, data). O Odoo aplica o mesmo casamento e o radar.
* **Resultado:** relatório **Compras inteligentes › Ofertas encontradas** e coluna **"Melhor preço encontrado (onde)"** na Lista de compras.

## 35.4. Requisitos não funcionais
* **Segurança:** cada integração tem **token próprio** (gerado e trocável na tela, guardado como parâmetro protegido); a API aceita só HTTPS; valida que a origem é **fornecedor cadastrado e marcado como confiável**; limite de requisições por minuto; tudo registrado (quem enviou, quando, quantos itens).
* **Estabilidade:** robôs e leitura de imagem rodam **fora do processo do PDV** (contêiner do coletor e fila de jobs); falha de um fornecedor não para os outros; tempo máximo por fonte.
* **Usabilidade:** o comprador nunca vê robô, código ou log — só a Lista de compras com o melhor preço e de onde veio, e a fila curta "Cotações para revisar".
* **LGPD:** guardar só o necessário da mensagem (itens e preços); o arquivo original fica 30 dias e é apagado.
* **Riscos:** raspagem de Instagram pode violar os termos e ser bloqueada a qualquer momento (já registrado na Etapa 18); a conexão do WhatsApp por QR Code é não oficial (ver 35.2.a).

## 35.5. Critérios de aceite
1. A tela **WhatsApp (conectar)** mostra o QR Code; depois de ler no celular (Dispositivos conectados), a tela passa a mostrar "Conectado" com o número.
2. Fornecedor cadastrado manda "Cebola kg 3,50" no WhatsApp do bar → em até 1 min aparece no Radar de preços com origem WhatsApp.
3. Mensagem de número não cadastrado (cliente, grupo, família) não gera preço e **não fica gravada**.
4. Celular desconectado → aviso na Saúde do sistema e no Painel do dono em até 10 min.
5. Chamada à API sem token ou com token errado é recusada (401) e registrada.
6. Coletor fora do ar ou site lento não afeta o tempo de resposta do PDV (teste de carga simples).
7. A Lista de compras mostra o melhor preço encontrado e a fonte.
8. Instagram é lido 1 vez por dia, no horário configurado.

---

# ETAPA 36 — QR CODE EXPRESSO DE BEBIDAS (REPETIR COM 1 TOQUE)

> **🤖 CHECKPOINT:** *"Na Etapa 36 vamos criar um segundo QR Code em cada mesa, só de bebidas: o cliente vê as bebidas que a mesa já pediu (cada uma separada), repete só a que quiser com 1 toque, ou escolhe outra no cardápio de bebidas, e o pedido vai direto para o bar. Implementar ativo, desativado ou pular?"*

*Origem: PRD "QR Code Expresso de Bebidas" (incorporado em 18/11/2026), ajustado aos nomes reais do código.*

## 36.1. Identificação das bebidas
* **Sem campo novo `is_bebida`**: o cadastro já tem o **tipo de consumo** (Etapa 12). Bebida = `boteco_tipo_consumo` em (`bebida_giro`, `garrafa`, `agua`). Criar só o campo calculado e armazenado `boteco_e_bebida` (com opção de marcar à mão quando o tipo não estiver preenchido), usado no filtro.
* Subcategorias do cardápio de bebidas = **Categorias do tablet** já existentes (Cervejas, Chopes, Drinks, Sem álcool…).
* **Fechada × preparada** (decisão do dono, 18/11/2026) — novo campo no produto `boteco_bebida_preparada` (Sim/Não):
  * **Fechada** (cerveja long neck/600 ml, lata, refrigerante, água): o garçom **abre na frente do cliente**; se vier a mais, **a mercadoria volta para o estoque**. → **sem teto**.
  * **Preparada** (caipirinha, drinks, doses, suco natural e **chope** — decidido pelo dono: é tirado na hora e não volta): → **com teto** por envio (36.3).
  * Preenchimento automático na primeira vez: categoria/tipo de consumo `bebida_giro` com setor Bar e ficha técnica (kit) ou nome contendo "chope", "caipi", "drink", "dose", "suco" = preparada; o resto = fechada. O dono confere e ajusta item a item no cadastro.

## 36.2. Dois QR Codes por mesa (`boteco_cardapio/report/qr_mesas_report.xml`)
* O cartão de cada mesa passa a ter **dois códigos identificados visualmente**: **"Cardápio completo"** e **"🍺 Bebidas rápido"**.
* O 2º usa o **mesmo endereço do autoatendimento da mesa** com o parâmetro `modo=bebidas`. (O PRD de origem cita `/mesa/<token_mesa>`; no sistema, a mesa é identificada pelo `table_identifier` do autoatendimento do Odoo — manter esse formato.)

## 36.3. Regras no servidor (`boteco_autoatendimento`)
* `controllers/mesa.py`: com `modo=bebidas`, devolver duas listas:
  1. **Suas bebidas na mesa** — cada bebida já pedida na sessão atual da mesa, **uma linha por bebida**, com a **última quantidade pedida** (ex.: Chope 300 ml — último pedido: 2 · Caipirinha — último pedido: 1). Amplia o "Pedir de novo" que já existe (hoje mostra só o produto, sem a última quantidade).
  2. **Cardápio de bebidas** — só itens com `boteco_e_bebida`, agrupados por categoria do tablet.
* **Envio direto, sem quarentena:** pedido com origem `qr_bebidas` **não passa pelo motor N+X** (Etapa 14) e vai **direto para o bar** (ticket na impressora do setor Bar e KDS), entrando na conta da mesa.
* **Regras decididas pelo dono (18/11/2026):**
  * **QR de bebidas sempre disponível, sem liberação do garçom:** nenhum celular precisa ser liberado para pedir pelo QR de bebidas (diferente do QR do cardápio completo, Etapa 4). Continuam valendo as travas que não dependem do garçom: o pedido só sai **de dentro da rede Wi-Fi do bar** e o QR só vale para a **mesa aberta e a sessão atual** (código de sessão que muda a cada abertura — foto antiga do QR não pede).
  * **Bebida fechada (cerveja, lata, refrigerante, água): sem teto** — o garçom abre na frente do cliente e o que sobrar volta ao estoque.
  * **Bebida preparada (drinks, caipirinhas, doses, chope): com teto por envio.** Acima do teto, **só as preparadas daquele envio** esperam a confirmação do garçom (tela de conferência da Etapa 16); as fechadas do mesmo envio saem na hora. Teto padrão = o limite de bebidas da Etapa 14 (`max(4, 2 × pessoas + 2)`), configurável na Central de Recursos (ex.: "no máximo 6 drinks por envio").
  * **Anti-toque repetido e trava de envio duplo** (`anti_burst.js`, Etapa 16) — **mantém**.
  * **Confirmação de idade (+18)** na primeira bebida alcoólica da mesa — **mantém** (obrigação legal; o pedido espera o garçom só nessa primeira vez da mesa, não a cada pedido).

## 36.4. Tela do cliente (`boteco_mesa.js` / `boteco_mesa.xml`)
* Com `modo=bebidas`, abre direto na visão de bebidas:
  * **Seção 1 — "Suas bebidas na mesa"** (só se já houve bebida): uma linha por bebida com o atalho **"+2"** (a última quantidade) e o seletor **– / +**. O cliente toca só no que quer repetir.
  * **Seção 2 — "Todas as bebidas"**: catálogo filtrado (sem comidas, porções e sobremesas), com busca rápida e **– / +**.
  * **Barra fixa embaixo:** resumo do que foi escolhido e botão **"Enviar para o bar"** (1 toque).
* Respeita tema, letra grande, ofertas relâmpago e happy hour já existentes.

## 36.5. Critérios de aceite
1. O PDF de QR Codes gera os **dois códigos** por mesa, identificados.
2. Mesa que pediu 2× Chope e 1× Caipirinha: ao ler o QR de bebidas, as duas aparecem **separadas**; dá para repetir só a caipirinha (1 toque + enviar) ou só os 2 chopes.
3. Só bebidas aparecem no cardápio desse QR.
4. **"Enviar para o bar"** não cai na tela de conferência do garçom (quarentena), sai na impressora do bar e entra na conta da mesa.
5. A primeira bebida alcoólica da mesa ainda pede a confirmação de idade.
6. Dois toques rápidos em "Enviar" geram **um** pedido só.
7. Celular novo pede pelo QR de bebidas **sem** o garçom liberar; fora da rede do bar ou com foto de uma sessão antiga, não pede.
8. Mesa de 4 pessoas pede **20 latas** de refrigerante de uma vez: sai direto para o bar (sem teto).
9. Mesa de 4 pessoas pede **12 caipirinhas** (teto padrão 10): as caipirinhas esperam a confirmação do garçom; as cervejas do mesmo envio saem na hora.
10. Flag `qr_bebidas` desligada: o PDF volta a ter um código só e `modo=bebidas` abre o cardápio normal.

---

# PARTE 2 — ITENS DESCARTADOS (E POR QUÊ)

| Recurso pago | Decisão | Motivo |
| :--- | :--- | :--- |
| Leitor de código de barras (Barcode) | Não desenvolver | Contagem pelo celular e QR nas transferências já cobrem o uso do boteco. |
| KDS do Odoo (Preparation Display) | Não desenvolver | O KDS próprio (Etapas 5, 15 e 21) é mais completo. |
| WhatsApp oficial (Enterprise) | Não desenvolver agora | Links `wa.me` resolvem sem custo; integração com provedor fica para quando houver contrato. |
| Studio, Sign, Documents | Não desenvolver | Não resolvem dor do boteco hoje. |
| Desinstalar o `boteco_b2b` (PRD de simplificação) | Trocado por **esconder com chave** | Painel do dono e Fiscal dependem dele; desinstalar removeria os dois com dados (Etapa 34.2). |
| Campo novo `is_bebida` (PRD do QR de bebidas) | Trocado pelo **tipo de consumo** que já existe | Evita cadastro duplicado (Etapa 36.1). |

---

# PARTE 3 — ORDEM SUGERIDA E ESTIMATIVA

| Ordem | Etapa | Esforço estimado |
| :--- | :--- | :--- |
| 1 | 26 + 32 Ajuda rápida e OdooBot | Médio (painel, busca, 40 artigos, script de fotos) |
| 2 | 33 Primeiros passos (usa os artigos da 26) | Médio |
| 3 | 34 Simplificação do PDV e perfis | Pequeno/Médio (configuração e permissões) |
| 4 | 36 QR Code expresso de bebidas | Médio |
| 5 | 31 Fidelidade | Pequeno (configuração + integração) |
| 6 | 27 Reservas | Grande |
| 7 | 28 Conferência de cartões e Pix | Grande (leitores de extrato por adquirente) |
| 8 | 35 Cotações por WhatsApp e coletor externo | Grande (serviço externo + fila) |
| 9 | 30 Checklists e manutenção | Médio |
| 10 | 29 Escala e ponto | Grande |

### Decisões do dono (18/11/2026)
| Etapa | Decisão |
| :--- | :--- |
| 35 | **Instagram 1 vez por dia** (padrão 8:00); sites 2 vezes por semana. |
| 35 | **WhatsApp conectado por QR Code** (como o WhatsApp Web: *Dispositivos conectados*), via Evolution API; lê só mensagens de fornecedores cadastrados. |
| 36 | **QR de bebidas sempre disponível, sem liberação do garçom** (continua exigindo a rede do bar e a sessão atual da mesa). |
| 36 | **Sem teto** para bebida fechada (cerveja, lata, refrigerante, água — o garçom abre na frente e o que sobra volta); **com teto** para bebida preparada (drinks, caipirinhas, doses, chope). |
| 35 | **Conectar o WhatsApp do bar** (número do bar), não o número pessoal do dono. |
| 36 | **Chope conta como bebida preparada** (com teto): é tirado na hora e não volta ao estoque. |

### Situação da implementação (18–19/11/2026)
Todas as etapas foram implementadas **ativas** (chave ligada na Central de Recursos), com testes automáticos (265 passando) e conferência no navegador.

| Etapa | Módulo | Observação |
| :--- | :--- | :--- |
| 26 + 32 | `boteco_base` (+ artigos em cada módulo) | Ajuda rápida (F1 / Ctrl+K), OdooBot desligado |
| 33 | `boteco_base` | Primeiros passos |
| 34 | vários | B2B escondido por chave; contador; PDV enxuto |
| 36 | `boteco_autoatendimento`, `boteco_cardapio` | QR de bebidas. Corrigido junto: pedido do celular não muda mais o nº de pessoas da mesa |
| 31 | `boteco_fidelidade` | Programas modelo **desligados** (o dono liga o que quiser). 10 chopes = 9 pagos + o 10º grátis, que entra sozinho |
| 27 | `boteco_reservas` | Sinal por Pix em chave separada, **desligada** |
| 28 | `boteco_conciliacao` | Leitor de extrato reconhece o cabeçalho sozinho (ou configurado por maquininha); banco por OFX |
| 35 | `boteco_cotacoes` + contêineres `evolution` e `coletor` (perfis opcionais) | Ligar no servidor: `scripts/ligar_cotacoes.sh` (ver `docs/whatsapp.md`). Instagram passou para 1x por dia (8:00, configurável) |
| 30 | `boteco_checklists` | Modelos prontos vêm **guardados** ("Usar este modelo"); planos de manutenção já criados |
| 29 | `boteco_escala` | Ponto em `/boteco/ponto` (atalho na tela de PIN) |

### Decisões em aberto (perguntar no checkpoint da etapa)
| Etapa | Decisão | Sugestão |
| :--- | :--- | :--- |
| 34 | Desinstalar de vez o B2B no futuro? | Só depois de separar as dependências do Painel e do Fiscal |

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

**Assistente de configuração / primeiros passos:**
[NN/g – Wizards](https://www.nngroup.com/articles/wizards/) · [Kompassify – onboarding wizard guide](https://kompassify.com/blog/onboarding-wizard-guide) · [saasui.design – onboarding checklist](https://www.saasui.design/blog/saas-onboarding-checklist-ux-patterns) · [Microsoft – User Assistance (wizards)](https://learn.microsoft.com/en-us/previous-versions/ms997609(v=msdn.10)) · [PatternFly – wizard](https://patternfly.org/components/wizard/design-guidelines) · [LogRocket – quando não usar wizard](https://blog.logrocket.com/ux-design/creating-setup-wizard-when-you-shouldnt/) · [Appcues – onboarding checklist](https://appcues.com/blog/customer-onboarding-checklist) · [Supademo – product onboarding checklist](https://supademo.com/blog/product-onboarding-checklist) · [Lightspeed – getting started](https://k-series-support.lightspeedhq.com/hc/articles/1260805671909) · [SkyTab – POS install checklist](https://www.skytab.com/blog/pos-system-install-checklist) · [Lavu – restaurant POS setup](https://lavu.com/how-to-set-up-a-pos-system-for-a-restaurant) · [Platter – setup launch checklist](https://intercom.help/platter-management-inc/en/articles/12947684-platter-setup-launch-checklist)

**OdooBot:**
[Fórum Odoo – desligar o OdooBot](https://www.odoo.com/forum/help-1/odoo-12-get-rid-of-that-odoo-bot-144178)
