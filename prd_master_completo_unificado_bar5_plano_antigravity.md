# PRD MASTER UNIFICADO E PLANO DE EXECUÇÃO INTERATIVO EM ETAPAS (ANTIGRAVITY)

## Ecossistema Boteco Raiz (`Bar5` — Odoo 17 Community All-in-One + Central de Feature Flags)

| Atributo do Documento | Detalhamento Técnico, Arquitetural e Operacional |
| :--- | :--- |
| **Projeto Alvo** | `Bar5` (Boteco Raiz — Odoo 17 Community + OWL + PostgreSQL + Docker + Nginx + ESC/POS) |
| **Fontes Unificadas** | 1. **Código Base `Bar5`** (Etapas 0 a 10) \| 2. **PRD Validação Inteligente de Pedidos** (4 páginas) \| 3. **PRD Master Completo Food Service** (32 páginas / 17 Módulos / Benchmark SisFood +600 recursos) \| 4. **Expansão Industrial de Congelados (Bar + B2B)** \| 5. **Inteligência de Compras via Instagram, Imagem/PDF e Radar de Preços**. |
| **Governança de Recursos** | **Tela Central de Habilitação de Recursos (`boteco.central.recursos`):** Todos os módulos e sub-recursos possuem chaves Liga/Desliga (*Feature Flags*) na interface para o dono ativar ou desativar a qualquer momento sem alterar código. |
| **Modo de Execução** | **Interativo Passo a Passo (Human-in-the-Loop):** O agente Antigravity DEVE perguntar ao usuário antes de cada etapa/recurso se deve **Implementar Completo**, **Implementar Desativado na Tela de Flags** ou **Pular**. |

---

# PARTE 0: PROTOCOLO DE EXECUÇÃO INTERATIVA PARA O AGENTE ANTIGRAVITY (OBRIGATÓRIO)

> **REGRA DE OURO PARA O AGENTE ANTIGRAVITY (LEIA ANTES DE TOCAR NO CÓDIGO):**
> Este PRD contém um ecossistema empresarial completo (25 Etapas cobrindo os 17 módulos do PRD Master + Produção de Congelados + Compras via Instagram/PDF). Como o proprietário pode optar por **não implementar** determinados recursos agora, você está **ESTRITAMENTE PROIBIDO** de sair alterando todos os módulos de uma só vez sem confirmação.
>
> **Fluxo Obrigatório a Cada Etapa:**
> 1. **Apresente o Resumo da Etapa:** Antes de iniciar qualquer Etapa (da Etapa 11 à Etapa 25), mostre ao usuário os sub-recursos daquela etapa.
> 2. **Faça a Pergunta de Decisão Passo a Passo:**
>    *"Estamos na **Etapa [X] — [Nome da Etapa]**. Ela inclui os seguintes recursos:*
>    *- `[FLAG_A]`: [Descrição curta]*
>    *- `[FLAG_B]`: [Descrição curta]*
>    *Como você deseja prosseguir com cada item?*
>    *1️⃣ **Implementar e já deixar ATIVO** por padrão na Tela de Recursos.*
>    *2️⃣ **Implementar no código, mas deixar DESATIVADO** na Tela de Recursos (para você ligar no futuro quando quiser).*
>    *3️⃣ **PULAR este recurso** (não alterar o código agora)."*
> 3. **Garanta a Verificação da Feature Flag no Código:** Todo recurso novo implementado no Python ou JavaScript/OWL DEVE checar se a respectiva flag está ativa na **Tela Central de Recursos** (`company.boteco_flag_<recurso>`) antes de rodar sua regra de negócio.
> 4. **Valide os Testes:** Ao concluir a etapa aprovada pelo usuário, rode `./scripts/testar.sh` e reporte o resultado antes de fazer a pergunta da próxima etapa.

---

# PARTE 1: O QUE VAMOS CONSTRUIR (OS 4 PILARES + MELHORIAS DO PRD MASTER DE 32 PÁGINAS)

## 1. Detalhamento dos Itens 1, 2, 3 e 4 + Melhorias do PRD Master

### 1.1. Item 1 — Ocupação da Mesa, Validação Inteligente de Pedidos ($N+X$), Z-Score e Alerta de Quarentena (`boteco_autoatendimento` + `boteco_pos` + `boteco_kds`)
* **O que o código atual (`Bar5`) faz hoje:**
  * `addons/boteco_autoatendimento/models/pos_order.py` valida apenas teto fixo (`15 itens` ou `R$ 500,00`), sem olhar quantas pessoas estão na mesa e sem diferenciar 10 chopes de 10 pratos individuais.
  * `addons/boteco_pos/models/restaurant_table.py` abre a mesa sem inicializar a contagem de clientes com a capacidade padrão (`seats`).
  * `addons/boteco_kds/models/pos_order.py` cria os cards de KDS e enfileira a impressão imediatamente, mesmo quando o pedido deveria ficar retido em quarentena.
* **O que vamos construir (integrando PRD Validação + Módulos 4, 6 e 7 do PRD Master):**
  1. **Ocupação Padrão na Abertura da Mesa (`flag_ocupacao_padrao_mesa`):** Ao abrir a mesa, `boteco_clientes_atuais` recebe automaticamente `table.seats` (capacidade física cadastrada), permitindo ao garçom confirmar com 1 toque ou ajustar na hora. Quando mesas são agrupadas/juntadas (Módulo 4.2 do PRD Master), o sistema soma automaticamente o $N$ das mesas unidas.
  2. **Regra do Tablet Neutro e UX Anti-Erro (`flag_tablet_neutro_anti_burst`):** O cliente no tablet **jamais** vê botão para alterar o número de pessoas na mesa. Além disso, o seletor `+` aplica *throttle* de 350ms a partir da 3ª unidade do mesmo prato (*Stepper Anti-Burst* — Módulo 6.2), exibe etiqueta clara de rendimento (*"Serve até 3 pessoas"*) e trava o botão "Enviar" no primeiro toque (*Submit Lock* + chave de idempotência UUID).
  3. **Motor Dinâmico de Tolerância ($N+X$) e Bloqueio Estrito (*Hard Hold* — `flag_quarentena_pedidos_anomalos`):**
     * Pedidos anômalos entram em `boteco_status_aprovacao = 'aguardando'` e **jamais são impressos na cozinha ou bar** até liberação humana.
     * **Regra 1 (Pratos Principais na Rodada):** $E_{\text{prato}} = \sum (Q_{\text{indiv}} \times 1) + \sum (Q_{\text{comp}} \times R)$. Limite dinâmico: $L_{\text{rodada\_prato}} = N + \max(1,\; \lfloor N \times 0,25 \rfloor)$.
     * **Regra 2 (Saturação Acumulada em 45 min):** Soma todos os pratos pedidos nos últimos 45 min na mesa ($E_{45\text{min}}$). Bloqueia se $E_{45\text{min}} + E_{\text{atual}} > \lceil N \times 1,5 \rceil + 1$.
     * **Regra 3 (Repetição Acidental do Mesmo SKU):** Para pratos e sobremesas, bloqueia se $Q_{\text{sku}} \ge 4$ em mesas de $N \le 3$ pessoas ou se $Q_{\text{sku}} > \min(N + 1,\; \text{maxPorRodadaSKU})$.
     * **Regra 4 (Bebidas de Giro vs. Garrafas Compartilhadas):** Para chopes/latas/doses: $L_{\text{beb\_indiv}} = \max(4,\; N \times 2 + 2)$ (ou $4 \times N$ conforme parametrização). Para garrafas de vinho/destilados: $L_{\text{vinho}} = \lceil N / 2 \rceil$.
     * **Regra 5 (Anomalia Financeira e Z-Score — `flag_validacao_zscore_ticket`):** Calcula média histórica ($\mu_{\text{ticket}}$) e desvio padrão ($\sigma_{\text{ticket}}$) dos últimos 90 dias. Bloqueia se o envio único ultrapassar $N \times (\mu_{\text{ticket}} + 2,5 \times \sigma_{\text{ticket}})$ ou $3 \times N \times \text{TicketMedio}$.
  4. **Alerta Unificado em Tempo Real com Lock de Concorrência (`aprovacoes.js`):**
     * Dispara modal instantâneo via WebSocket (`bus.bus`) para todos os garçons, atendentes e caixas com 3 botões: **[1. Ajustar Nº de Clientes (`+`/`-`) e Liberar]**, **[2. Corrigir Quantidade do Item (ex.: 10 $\rightarrow$ 1) e Liberar]** e **[3. Liberar Exceção Sem Alterar Clientes]**.
     * Assim que um funcionário resolve, o evento `boteco_anomalia_resolvida` fecha o alerta na tela de todos os outros funcionários em menos de 1 segundo (Módulo 7.5 do PRD Master).

### 1.2. Item 2 — Inteligência de Associação, Correlação (Vinho/Água) e Utensílios na Impressão (`boteco_kds` + `boteco_base`)
* **O que o código atual (`Bar5`) faz hoje:**
  * `addons/boteco_kds/models/boteco_kds.py` formata o cupom térmico listando apenas `quantidade x nome_produto`, sem controlar se a mesa já recebeu copos, taças, pratos de compartilhamento ou se pediu vinho sem água.
* **O que vamos construir (integrando Módulos 8 e 9 do PRD Master):**
  1. **Máquina de Estados da 1ª Cerveja e Delta de Clientes (`flag_insumo_copos_primeira_cerveja`):**
     * A comanda guarda `boteco_copos_cerveja_enviados`.
     * Na **1ª cerveja** (600ml, litrão, balde), imprime caixa destacada no Bar: `>>> 1o PEDIDO DE CERVEJA DA MESA — LEVAR [N] COPOS / TULIPAS <<<` e atualiza o contador para $N$.
     * Na **2ª cerveja em diante**, omite o alerta de copos.
     * Se **chegarem mais clientes na mesa** ($N > \text{copos\_enviados}$), na próxima cerveja imprime apenas a diferença: `>>> CHEGARAM +[DELTA] CLIENTES NA MESA — LEVAR +[DELTA] COPOS EXTRAS <<<`.
  2. **Correlação Vinho $\rightarrow$ Água Mineral + Taças/Balde de Gelo (`flag_correlacao_vinho_agua`):**
     * No cupom do Bar/Adega: imprime `>>> ENVIAR [N] TACAS DE VINHO + SACA-ROLHAS <<<` (e `+ BALDE COM GELO E AGUA` se for vinho branco, rosé ou espumante).
     * No Tablet do Cliente (Cross-Sell Suave opcional): pergunta antes de enviar se deseja adicionar Água Mineral com ou sem gás.
     * No Terminal do Garçom: se o pedido de vinho entrou sem Água Mineral na comanda, dispara alerta visual: *"🍷 Mesa [X] pediu vinho e está sem água. Ofereça Água Mineral!"*.
  3. **Utensílios de Pratos Compartilhados e Finger Food (`flag_insumo_pratos_compartilhados`):**
     * Tábuas/Picanha na Chapa imprimem na cozinha: `>>> MONTAR C/ [N] PRATOS RASOS QUENTES + [N] KITS TALHERES + PEGADOR <<<`.
     * Lanches/Costelinha BBQ imprimem: `>>> ENVIAR CESTA DE GUARDANAPOS REFORCADA + LUVAS/SACHES p/ [N] PESSOAS <<<` (CORR-08 do PRD Master).
  4. **Sequenciamento Hold & Fire de Entradas, Pratos e Sobremesas (`flag_hold_fire_sobremesa_2_tempo`):**
     * Quando o cliente pede Prato Principal + Sobremesa (sorvete/petit gâteau) juntos, a sobremesa fica retida em status `HOLD_2_TEMPO` (ou recebe tarja destacada de 2º tempo) para só ser preparada quando o prato principal for finalizado, evitando que derreta (CORR-05 e CORR-06 do PRD Master).

### 1.3. Item 3 — Capacidade Finita de Produção de Congelados, Câmara Fria e Alocação Bar vs. Revenda B2B (`boteco_cozinha_central` + `boteco_b2b`)
* **O que o código atual (`Bar5`) faz hoje:**
  * `addons/boteco_cozinha_central/wizard/boteco_plano_producao.py` calcula a produção sem limite diário de equipamento/equipe, sem checar o volume disponível nos freezers e sem proteger o estoque mínimo que o próprio bar precisa para operar à noite.
* **O que vamos construir:**
  1. **Capacidade Finita Diária por Produto e Cozinha (`flag_capacidade_finita_congelados`):** Campos `boteco_lote_max_diario` no produto e `boteco_capacidade_prod_diaria_kg` no armazém para nivelar as ordens de produção (`mrp.production`).
  2. **Controle Volumétrico de Freezers (`-18 °C` — `flag_controle_volume_freezer`):** Calcula em tempo real quantos litros estão ocupados nos freezers (`qty_available * boteco_volume_freezer_litros`) e impede que o Plano de Produção gere ordens que não cabem nas câmaras frias.
  3. **Reserva Exclusiva do Bar vs. Disponível B2B (`flag_reserva_estoque_bar_b2b`):** Campo `boteco_estoque_min_bar` que bloqueia pedidos de revenda B2B (`sale.order`) caso tentem consumir a cota de segurança do salão do bar.
  4. **Explosão Multinível de Insumos, Fator de Correção e Cocção (`flag_explosao_insumos_fator_coccao`):** Inspirado no Módulo 12.1 do PRD Master, adiciona na ficha técnica (`mrp.bom.line`) o **Fator de Correção/Limpeza** (perda no descasque/apara) e **Fator de Cocção** (perda de peso no fogo), além de avisar no Plano de Produção quais matérias-primas faltam no estoque antes de ligar o fogão.

### 1.4. Item 4 — Busca de Materiais de Compra via Leitura de Instagram, Imagem/PDF de Orçamento e Radar de Preços (`boteco_estoque` + `boteco_painel`)
* **O que o código atual (`Bar5`) faz hoje:**
  * `addons/boteco_estoque` só lê XML de NF-e após a compra faturada e monta lista de compras no WhatsApp usando fornecedor estático.
* **O que vamos construir:**
  1. **Importador Multimodal de Orçamentos em PDF e Imagem (`flag_leitor_orcamento_pdf_imagem`):** Wizard `boteco.importar.orcamento` que recebe PDFs de fornecedores ou fotos de tabelas/encartes enviadas no WhatsApp, extraindo itens e preços via parser nativo (`pypdf`/Regex) ou Vision LLM (`Gemini 2.5 Flash` / `OpenAI Vision`).
  2. **Monitoramento Automatizado de Ofertas no Instagram (`flag_monitor_instagram_fornecedores`):** Cron que lê os posts recentes dos `@perfis` de atacadistas/hortifrutis/frigoríficos cadastrados em `res.partner.boteco_instagram_handle` (via `instaloader`/JSON parser) e extrai as promoções do dia.
  3. **Histórico de Preços e Radar de Preços Interessantes (`flag_radar_precos_oportunidade`):** Tabela `boteco.historico.preco` que calcula Média Móvel de 60 dias, Menor Preço de 90 dias, destaca quedas $\ge 10\%$ (`preco_interessante = True`) e cruza com as fichas técnicas (`mrp.bom`) dos congelados para informar no Painel do Dono: *"Comprar este insumo hoje economiza R$ X,XX na produção de congelados (e há Y litros livres no freezer)"*.

### 1.5. Item 5 — Melhorias Adicionais do PRD Master (32 Páginas) Incorporadas como Módulos Opcionais (Com Feature Flags)
Para que nenhuma melhoria do seu **PRD Master** fique de fora, mapeamos todos os recursos avançados dos Módulos 3, 4, 5, 6, 9, 10, 11, 12, 13 e 14 como etapas modulares controladas pela **Tela de Habilitação de Recursos**:
* **Módulo 3 (PDV Avançado):** Atalhos rápidos `F1` a `F12` (`flag_pdv_atalhos_f1_f12`), Emissão de Fichas Avulsas por unidade com código de barras (`flag_pdv_fichas_avulsas`), Leitura de Balança Serial / Etiqueta EAN-13 de peso variável prefixo `2` (`flag_pdv_balanca_ean13`), Produtos Fracionados Meio a Meio / Pizza com cobrança pelo maior valor ou média (`flag_pdv_fracionamento_meio_a_meio`), e Edição de Forma de Pagamento pós-venda no turno aberto (`flag_pdv_editar_pagamento_pos_venda`).
* **Módulo 4 (Salão e Portaria):** Validador de Saída na Portaria por leitura de comanda/QR Code exibindo tela Verde PAGA ou Vermelha PENDENTE (`flag_portaria_validador_saida`) e Agrupamento/Junção de Mesas com pré-visualização comparativa (`flag_salao_juncao_mesas`).
* **Módulo 5 e 6 (Garçom, Smart POS e Tablet):** Favoritos de 1 toque + Tags rápidas de observação (`[Sem Cebola]`, `[Ao Ponto]`, `[Gelo e Limão]` — `flag_garcom_tags_rapidas`), Integração DeepLink para cobrança direta em maquininhas Smart POS sem digitar valor (`flag_smartpos_deeplink`), Screensaver promocional e Botões de Chamada Qualificada no Tablet (`[Trazer Gelo/Copos]`, `[Pedir Conta]` — `flag_tablet_chamada_qualificada`).
* **Módulo 9 (KDS Avançado):** Totalizador de Produção / Grelha na lateral do KDS somando itens iguais abertos (`flag_kds_totalizador_grelha`), Coordenação de Tempo de Preparo / Pacing entre praças (`flag_kds_pacing_pracas`) e suporte a teclado numérico USB (*Bump Bar* — `flag_kds_bump_bar_teclado`).
* **Módulo 10 e 11 (WhatsApp IA, CRM e Delivery):** Webhook para Agente de IA no WhatsApp e Régua de Recuperação de Clientes Inativos/Aniversariantes (`flag_crm_whatsapp_ia_recuperacao`) + Gestão de Delivery, Taxa por Bairro e Acerto de Motoboys (`flag_delivery_roteirizacao_motoboy`).
* **Módulo 13 e 14 (Fiscal NFC-e e Financeiro Pix/Rateio):** Emissão/Integração NFC-e com Contingência Offline (`flag_fiscal_nfce_contingencia`), Pix Dinâmico com baixa automática por Webhook (`flag_financeiro_pix_webhook`) e Rateio Configurável da Taxa de Serviço 10% entre Garçom, Cozinha e Casa (`flag_financeiro_rateio_gorjeta`).

---

# PARTE 2: CATÁLOGO COMPLETO DE REFERÊNCIAS DE CÓDIGO DO GITHUB

O agente Antigravity e a equipe de engenharia devem utilizar os seguintes projetos e bibliotecas open-source do GitHub como base de implementação no `Bar5`:

| Módulo / Recurso | Repositório Oficial no GitHub | O Que Reaproveitar / Adaptar no `Bar5` (Odoo 17 Python/OWL) |
| :--- | :--- | :--- |
| **1. Feature Flags e Configuração Modular** | `OCA/server-ux` & `odoo/odoo` (`res.config.settings`) | Padrão `TransientModel` herdando `res.config.settings` + painel visual customizado de chaves Liga/Desliga por empresa (`res.company`). |
| **2. Quarentena de Pedidos e Salão/POS** | `OCA/pos` (`pos_order_Hold`, `pos_restaurant_base`) | Interceptação do ciclo de envio do pedido antes do disparo para impressoras de rede e sincronização via `bus.bus`. |
| **3. Impressão ESC/POS, Fichas e Código de Barras** | `python-escpos/python-escpos` | Comandos hexadecimais ESC/POS de inversão de cor (fundo preto para alerta de 1ª cerveja), corte parcial (`GS V 66`) para fichas avulsas e impressão de barcode EAN13/CODE128. |
| **4. Balança Checkout e Etiqueta EAN-13 (Prefixo 2)** | `OCA/pos` (`pos_scale`) & `odoo/odoo` (`barcode.nomenclature`) | Regras de nomenclatura de código de barras padrão brasileiro `2LLLLLPPPPPC` (5 dígitos produto + 5 dígitos peso/preço) e leitura serial Toledo/Filizola. |
| **5. Capacidade Finita de Produção e Freezers** | `OCA/manufacture` (`mrp_workorder_capacity`) & `frePPLe/frepple` | Nivelamento de ordens `mrp.production` baseado em restrições finitas de capacidade diária e cubagem de armazenamento frio (`stock.location`). |
| **6. Leitura Automatizada de Instagram** | `instaloader/instaloader` | Coleta limpa em Python de legendas e imagens de posts públicos de perfis de fornecedores (`Profile.from_username(L.context, handle).get_posts()`). |
| **7. Extração de Tabelas e Preços em PDF e Imagem** | `DS4SD/docling`, `py-pdf/pypdf`, `PaddlePaddle/PaddleOCR` | Pipeline de extração documental combinando `pypdf` para PDFs nativos e API Multimodal (`Gemini 2.5 Flash` Structured JSON) para fotos de encartes. |
| **8. Radar Histórico de Preços e Alertas** | `dgtlmoon/changedetection.io` | Lógica de detecção de queda percentual de preços contra média móvel e disparo de alertas de oportunidade de compra. |
| **9. Fiscal NFC-e / NF-e e Manifesto SEFAZ** | `OCA/l10n-brazil` (`l10n_br_oca`, `l10n_br_fiscal`, `erpbrasil.edoc`) | Estrutura de NCM, CFOP, ICMS-ST monofásico de bebidas frias, importação de XML e emissão de NFC-e/SAT. |
| **10. WhatsApp Bot IA e Notificações** | `EvolutionAPI/evolution-api` & `WhiskeySockets/Baileys` | Disparo e recebimento de mensagens/áudios via REST Webhook local integrado ao Kanban do PDV e à Lista de Compras. |

---

# PARTE 3: ARQUITETURA DA TELA DE HABILITAÇÃO DE RECURSOS (CENTRAL DE FEATURE FLAGS)

Antes de qualquer regra entrar em operação, o `Bar5` contará com o painel **"Configurações $\rightarrow$ Central de Recursos do Sistema (Liga/Desliga)"**. Todas as 22 chaves ficam armazenadas em `res.company` (permitindo configuração independente caso você tenha mais de uma unidade/loja no futuro) e expostas em uma tela organizada por abas.

### Mapa Geral das 22 Feature Flags do Sistema

| Código da Flag em `res.company` | Nome na Tela do Dono | Módulo Afetado | Padrão Inicial Sugerido |
| :--- | :--- | :--- | :--- |
| `boteco_flag_ocupacao_padrao_mesa` | Sugerir capacidade padrão (`seats`) na abertura da mesa | `boteco_pos` | **ATIVO (`True`)** |
| `boteco_flag_tablet_neutro_anti_burst` | Tablet Neutro (sem ajuste de clientes pelo cliente + trava anti-toque repetido) | `boteco_autoatendimento` | **ATIVO (`True`)** |
| `boteco_flag_quarentena_pedidos_anomalos` | **Motor de Quarentena ($N+X$):** Barrar pedidos fora do padrão e alertar Garçom/Caixa | `boteco_autoatendimento`, `boteco_kds` | **ATIVO (`True`)** |
| `boteco_flag_validacao_zscore_ticket` | Bloqueio por Anomalia Financeira (3x Ticket Médio / Z-Score) | `boteco_autoatendimento` | **ATIVO (`True`)** |
| `boteco_flag_insumo_copos_primeira_cerveja` | **Regra da 1ª Cerveja:** Imprimir aviso de $[N]$ copos no Bar (e delta de novos clientes) | `boteco_kds` | **ATIVO (`True`)** |
| `boteco_flag_correlacao_vinho_agua` | **Regra do Vinho:** Imprimir $[N]$ taças/balde no Bar e alertar garçom para oferecer Água | `boteco_kds`, `boteco_pos` | **ATIVO (`True`)** |
| `boteco_flag_insumo_pratos_compartilhados` | Imprimir $[N]$ pratos rasos/talheres em pratos compartilhados e guardanapos em lanches | `boteco_kds` | **ATIVO (`True`)** |
| `boteco_flag_hold_fire_sobremesa_2_tempo` | **Hold & Fire:** Reter sobremesa/sorvete para 2º tempo quando pedido junto com prato quente | `boteco_kds` | **ATIVO (`True`)** |
| `boteco_flag_capacidade_finita_congelados` | **Cozinha Central:** Limitar Plano de Produção pela capacidade máxima diária | `boteco_cozinha_central` | **ATIVO (`True`)** |
| `boteco_flag_controle_volume_freezer` | **Câmara Fria:** Limitar produção pelo espaço livre nos freezers (Litros) | `boteco_cozinha_central` | **ATIVO (`True`)** |
| `boteco_flag_reserva_estoque_bar_b2b` | **Proteção Bar vs. B2B:** Impedir que venda B2B consuma a reserva mínima do Bar | `boteco_b2b`, `boteco_cozinha_central` | **ATIVO (`True`)** |
| `boteco_flag_explosao_insumos_fator_coccao` | Fator de Correção/Cocção na Ficha Técnica e alerta de insumos faltantes | `boteco_cozinha_central` | **ATIVO (`True`)** |
| `boteco_flag_leitor_orcamento_pdf_imagem` | **Compras IA:** Leitura de Orçamentos em PDF e Foto/Imagem | `boteco_estoque` | **ATIVO (`True`)** |
| `boteco_flag_monitor_instagram_fornecedores` | **Compras IA:** Monitoramento de ofertas em perfis de Instagram de fornecedores | `boteco_estoque` | **ATIVO (`True`)** |
| `boteco_flag_radar_precos_oportunidade` | **Radar de Preços:** Histórico de cotações e alerta de economia p/ congelados | `boteco_estoque`, `boteco_painel` | **ATIVO (`True`)** |
| `boteco_flag_pdv_atalhos_f1_f12` | Atalhos rápidos de teclado `F1` a `F12` no PDV e edição de pagamento pós-venda | `boteco_pos` | *Opcional (`False`)* |
| `boteco_flag_pdv_fichas_avulsas` | Emissão de Fichas Avulsas individuais por item com código de barras | `boteco_pos` | *Opcional (`False`)* |
| `boteco_flag_pdv_balanca_ean13` | Leitura de etiquetas de balança EAN-13 (peso variável) e produtos meio a meio | `boteco_pos` | *Opcional (`False`)* |
| `boteco_flag_portaria_validador_saida` | Tela Validador de Saída na Portaria (Comanda Paga vs. Pendente) | `boteco_pos` | *Opcional (`False`)* |
| `boteco_flag_kds_totalizador_pacing` | Painel Totalizador de Grelha no KDS, Pacing de praças e atalhos Bump Bar | `boteco_kds` | *Opcional (`False`)* |
| `boteco_flag_crm_whatsapp_ia` | Webhook Agente WhatsApp IA e Régua de Recuperação de Clientes Sumidos | `boteco_cardapio`, `boteco_pos` | *Opcional (`False`)* |
| `boteco_flag_financeiro_pix_rateio` | Pix Dinâmico automático e Relatório de Rateio da Taxa de Serviço (Garçom/Cozinha/Casa) | `boteco_painel`, `boteco_pos` | *Opcional (`False`)* |

---

# PARTE 4: PLANO DE EXECUÇÃO PASSO A PASSO PARA O ANTIGRAVITY (ETAPAS 0 A 25)

## ETAPAS BASE JÁ EXISTENTES NO `Bar5` (ETAPAS 0 A 10 — VERIFICAÇÃO INICIAL)
* **Etapas 0 a 10:** Infraestrutura Docker/Nginx (`etapa-0.md`), Base/RBAC/PIN/Auditoria/ESC-POS (`etapa-1.md`), Cardápio/Happy Hour/Oferta Relâmpago (`etapa-2.md`), PDV Salão/Ociosidade/Couvert/Fechamento Cego (`etapa-3.md`), Autoatendimento QR/Tablet Base (`etapa-4.md`), KDS/Fila de Impressão/Contingência (`etapa-5.md`), Estoque/NF-e XML/Contagem Cega/CMV (`etapa-6.md`), Cozinha Central/Temperatura APPCC/Lotes (`etapa-7.md`), B2B Contratos/Recorrência/Romaneio (`etapa-8.md`), Painel do Dono/DRE (`etapa-9.md`), Exportação Fiscal/Modo Treinamento (`etapa-10.md`).

---

## ETAPA 11: Tela Central de Habilitação de Recursos / Feature Flags (`boteco_base`)

> **🤖 CHECKPOINT ANTIGRAVITY — PERGUNTE AO USUÁRIO ANTES DE INICIAR A ETAPA 11:**
> *"Posso criar agora na Etapa 11 a **Tela Central de Habilitação de Recursos (Liga/Desliga)** em `boteco_base` para que você tenha controle total na interface sobre quais funções do sistema ficam ativas ou desativadas?"*

### 11.1. Alterações de Código

#### Arquivo 1: `addons/boteco_base/models/res_company.py`
Adicionar todas as 22 flags booleanas e um método auxiliar `recurso_ativo(codigo_flag)` em `res.company`:

```python
# Em addons/boteco_base/models/res_company.py
# Adicionar os campos da Central de Recursos dentro de ResCompany(models.Model):

    # Grupo 1: Validação Inteligente de Pedidos e Salão
    boteco_flag_ocupacao_padrao_mesa = fields.Boolean(
        string="Sugerir Capacidade Padrão na Abertura da Mesa", default=True
    )
    boteco_flag_tablet_neutro_anti_burst = fields.Boolean(
        string="Tablet Neutro (Ocultar Clientes) + Anti-Toque Repetido (+)", default=True
    )
    boteco_flag_quarentena_pedidos_anomalos = fields.Boolean(
        string="Motor de Quarentena (N+X): Barrar Pedidos Anômalos e Alertar Garçom/Caixa", default=True
    )
    boteco_flag_validacao_zscore_ticket = fields.Boolean(
        string="Trava de Anomalia Financeira (3x Ticket Médio / Z-Score)", default=True
    )

    # Grupo 2: Utensílios na Impressão e Correlações de Consumo
    boteco_flag_insumo_copos_primeira_cerveja = fields.Boolean(
        string="1ª Cerveja: Imprimir Aviso de [N] Copos no Bar (e Delta de Novos Clientes)", default=True
    )
    boteco_flag_correlacao_vinho_agua = fields.Boolean(
        string="Vinho: Imprimir [N] Taças/Balde no Bar e Alertar Garçom p/ Oferecer Água", default=True
    )
    boteco_flag_insumo_pratos_compartilhados = fields.Boolean(
        string="Pratos Compartilhados/Lanches: Imprimir [N] Pratos Rasos e Cesta de Guardanapos", default=True
    )
    boteco_flag_hold_fire_sobremesa_2_tempo = fields.Boolean(
        string="Hold & Fire: Reter Sobremesa (2º Tempo) Quando Pedida Junto c/ Prato Principal", default=True
    )

    # Grupo 3: Cozinha Central de Congelados e Proteção Bar vs. B2B
    boteco_flag_capacidade_finita_congelados = fields.Boolean(
        string="Limitar Plano de Produção pela Capacidade Diária da Cozinha", default=True
    )
    boteco_flag_controle_volume_freezer = fields.Boolean(
        string="Controlar Espaço Físico Livre nos Freezers / Câmara Fria (Litros)", default=True
    )
    boteco_flag_reserva_estoque_bar_b2b = fields.Boolean(
        string="Proteger Reserva Mínima de Congelados do Bar Contra Vendas B2B", default=True
    )
    boteco_flag_explosao_insumos_fator_coccao = fields.Boolean(
        string="Explosão de Matéria-Prima Faltante e Fator de Cocção na Receita", default=True
    )

    # Grupo 4: Inteligência de Compras (Instagram, PDF/Imagem e Radar de Preços)
    boteco_flag_leitor_orcamento_pdf_imagem = fields.Boolean(
        string="Leitor de Orçamentos em PDF e Foto/Imagem (OCR / Vision IA)", default=True
    )
    boteco_flag_monitor_instagram_fornecedores = fields.Boolean(
        string="Monitoramento Automático de Ofertas no Instagram dos Fornecedores", default=True
    )
    boteco_flag_radar_precos_oportunidade = fields.Boolean(
        string="Radar de Preços Interessantes e Cálculo de Economia nos Congelados", default=True
    )

    # Grupo 5: Recursos Opcionais do PRD Master (PDV, Portaria, KDS, WhatsApp IA, Financeiro)
    boteco_flag_pdv_atalhos_f1_f12 = fields.Boolean(
        string="Atalhos de Teclado F1-F12 no PDV e Edição de Pagamento Pós-Venda", default=False
    )
    boteco_flag_pdv_fichas_avulsas = fields.Boolean(
        string="Emissão de Fichas Avulsas por Unidade com Código de Barras", default=False
    )
    boteco_flag_pdv_balanca_ean13 = fields.Boolean(
        string="Leitura de Balança / Etiqueta EAN-13 e Produtos Meio a Meio (Fracionados)", default=False
    )
    boteco_flag_portaria_validador_saida = fields.Boolean(
        string="Módulo Validador de Saída na Portaria (Comanda Paga vs. Bloqueada)", default=False
    )
    boteco_flag_kds_totalizador_pacing = fields.Boolean(
        string="KDS Avançado: Totalizador de Grelha, Sincronia de Praças (Pacing) e Bump Bar", default=False
    )
    boteco_flag_crm_whatsapp_ia = fields.Boolean(
        string="Agente de IA no WhatsApp e Régua de Recuperação de Clientes Sumidos", default=False
    )
    boteco_flag_financeiro_pix_rateio = fields.Boolean(
        string="Pix Dinâmico Automático e Relatório de Rateio da Taxa de Serviço (10%)", default=False
    )

    def boteco_recurso_ativo(self, nome_flag):
        """Verifica de forma segura se um recurso está habilitado na empresa atual."""
        self.ensure_one()
        campo = f"boteco_flag_{nome_flag}" if not nome_flag.startswith("boteco_flag_") else nome_flag
        return bool(getattr(self, campo, False))
```

#### Arquivo 2: `addons/boteco_base/views/res_company_views.xml` e `menus.xml`
Criar uma aba dedicada **"Central de Recursos (Liga/Desliga)"** no formulário da Empresa e uma ação direta no menu **Boteco Base $\rightarrow$ Habilitar / Desabilitar Recursos** com switches (`widget="boolean_toggle"`) divididos nos 5 grupos operacionais.

---

## ETAPA 12: Taxonomia Semântica de Consumo e Regras de Utensílios no Cardápio (`boteco_cardapio`)

> **🤖 CHECKPOINT ANTIGRAVITY — PERGUNTE AO USUÁRIO ANTES DE INICIAR A ETAPA 12:**
> *"Na Etapa 12 vamos adicionar no cadastro de produtos a classificação de consumo (`Prato Individual`, `Compartilhado`, `Sobremesa`, `Bebida Giro`, `Garrafa`, `Água`), o rendimento (`Serve Quantas Pessoas`) e a regra de utensílios (`Copo Cerveja`, `Taça Vinho`, `Pratos Rasos`, `Cesta de Guardanapos`). Deseja aplicar a Etapa 12 agora?"*

### 12.1. Alterações de Código
* Em `addons/boteco_cardapio/models/product_template.py`: adicionar `boteco_tipo_consumo`, `boteco_serve_pessoas`, `boteco_max_por_rodada_sku` e `boteco_regra_utensilio` (incluindo `copo_cerveja`, `taca_vinho`, `taca_vinho_gelo`, `pratos_compartilhados` e `guardanapo_reforcado`).
* Em `addons/boteco_cardapio/models/pos_config.py`: exportar esses campos para o frontend OWL do POS.
* Em `addons/boteco_cardapio/views/product_template_views.xml`: exibir os campos no formulário do produto.

---

## ETAPA 13: Ocupação Padrão na Abertura da Mesa e Junção Consolidada de Mesas (`boteco_pos`)

> **🤖 CHECKPOINT ANTIGRAVITY — PERGUNTE AO USUÁRIO ANTES DE INICIAR A ETAPA 13:**
> *"Na Etapa 13 temos 2 recursos para o Salão (`boteco_pos`):*
> *1. `boteco_flag_ocupacao_padrao_mesa`: Preencher automaticamente o número de clientes com a capacidade padrão da mesa na abertura.*
> *2. `boteco_flag_salao_juncao_mesas`: Agrupar/Juntar mesas somando a capacidade de clientes ($N_{\text{total}}$) para que grupos grandes possam pedir sem bloqueio indevido.*
> *Quais destes 2 recursos você deseja habilitar?"*

### 13.1. Alterações de Código
* Em `addons/boteco_pos/models/restaurant_table.py`:
  * Adicionar `boteco_clientes_atuais` e `boteco_mesa_principal_id` (para junção de mesas).
  * No método `action_boteco_abrir_mesa()`, se `company.boteco_recurso_ativo("ocupacao_padrao_mesa")` for verdadeiro, definir `boteco_clientes_atuais = rec.seats or 2`.
  * Criar método `action_boteco_agrupar_mesas(mesa_destino_id)` que soma `boteco_clientes_atuais` das mesas unidas (CASO-09 do PRD Master).

---

## ETAPA 14: Motor de Validação Inteligente ($N+X$), Z-Score e Quarentena Estrita (`boteco_autoatendimento`)

> **🤖 CHECKPOINT ANTIGRAVITY — PERGUNTE AO USUÁRIO ANTES DE INICIAR A ETAPA 14:**
> *"Na Etapa 14 vamos implementar o **Motor de Validação Inteligente ($N+X$) e Quarentena Estrita** em `boteco_autoatendimento/models/pos_order.py`. Ele inclui:*
> *1. `boteco_flag_quarentena_pedidos_anomalos`: Barrar pedidos fora do limite dinâmico ($N+1$ para pratos individuais, $\lceil N/R \rceil + 1$ para compartilhados, acumulado de 45 min e trava de repetição do mesmo prato).*
> *2. `boteco_flag_validacao_zscore_ticket`: Barrar pedidos que estourem $3\times$ o ticket médio por pessoa ou o Z-Score histórico.*
> *Como deseja configurar cada um destes 2 itens?"*

### 14.1. Alterações de Código
* Atualizar `addons/boteco_autoatendimento/models/pos_order.py` verificando `self.company_id.boteco_recurso_ativo("quarentena_pedidos_anomalos")` antes de reter o pedido.
* Implementar os métodos de resolução rápida acionados pelo garçom ou caixa:
  * `action_boteco_ajustar_clientes_e_aprovar(nova_qtd_clientes)`
  * `action_boteco_corrigir_item_e_aprovar(ajustes_linhas)`
  * `action_boteco_aprovar_pedido()` (exceção sem alterar clientes)
  * `action_boteco_rejeitar_pedido()`
* Enviar notificação broadcast via `bus.bus` na criação do bloqueio (`boteco_pedido_retido`) e no momento da resolução (`boteco_anomalia_resolvida` — fechando o popup nos demais terminais).

---

## ETAPA 15: Máquina de Utensílios na Impressão (1ª Cerveja/Copos, Vinho/Água/Taças) e Hold & Fire (`boteco_kds`)

> **🤖 CHECKPOINT ANTIGRAVITY — PERGUNTE AO USUÁRIO ANTES DE INICIAR A ETAPA 15:**
> *"Na Etapa 15 vamos configurar o roteamento inteligente de impressão e KDS (`boteco_kds`). Escolha quais regras deseja ativar:*
> *1. `boteco_flag_insumo_copos_primeira_cerveja`: Imprimir destaque de $[N]$ copos apenas na 1ª cerveja da mesa (e enviar copos extras se chegarem mais pessoas).*
> *2. `boteco_flag_correlacao_vinho_agua`: Imprimir $[N]$ taças + saca-rolhas/balde de gelo no pedido de vinho e alertar o garçom se a mesa não pediu Água Mineral.*
> *3. `boteco_flag_insumo_pratos_compartilhados`: Imprimir $[N]$ pratos rasos quentes/pegador em pratos compartilhados e cesta de guardanapos reforçada em lanches.*
> *4. `boteco_flag_hold_fire_sobremesa_2_tempo`: Marcar/reter sobremesas para o 2º tempo quando pedidas junto com prato principal."*

### 15.1. Alterações de Código
* Em `addons/boteco_kds/models/pos_order.py`: impedir que `_criar_pedidos_kds()` crie cards ou imprima enquanto `boteco_status_aprovacao == 'aguardando'`.
* Em `addons/boteco_kds/models/boteco_kds.py`: atualizar `_formatar_ticket()` checando cada uma das 4 flags acima na empresa antes de injetar os blocos de destaque no cupom térmico e disparar o alerta de água no `bus.bus`.

---

## ETAPA 16: Alerta Unificado na Tela do Garçom/Caixa (`aprovacoes.js`) e UX de Tablet Neutro (`boteco_mesa.js`)

> **🤖 CHECKPOINT ANTIGRAVITY — PERGUNTE AO USUÁRIO ANTES DE INICIAR A ETAPA 16:**
> *"Na Etapa 16 vamos atualizar as telas do Tablet do Cliente e do Terminal do Garçom/Caixa:*
> *1. `boteco_flag_tablet_neutro_anti_burst`: Garantir que o tablet não mostre controle de pessoas para o cliente, adicione trava de 350ms contra cliques repetidos no botão `+` e trave duplo clique no envio.*
> *2. **Modal Unificado de Quarentena (`aprovacoes.js`)**: Tela do garçom e caixa com botões para ajustar clientes (`+`/`-`) e liberar, corrigir quantidade do item de 10 para 1 ou liberar exceção.*
> *3. `boteco_flag_tablet_chamada_qualificada`: Botões de chamada qualificada no tablet (`[Trazer Copos/Gelo]`, `[Trazer Guardanapos]`, `[Pedir Conta Cartão/Pix]`).*
> *Quais destes 3 itens deseja habilitar?"*

### 16.1. Alterações de Código
* Atualizar `addons/boteco_autoatendimento/controllers/mesa.py`, `addons/boteco_autoatendimento/static/src/pos/aprovacoes.js` e `addons/boteco_autoatendimento/static/src/self_order/boteco_mesa.js`.

---

## ETAPA 17: Capacidade Finita de Produção de Congelados, Câmara Fria, Fator de Cocção e Proteção Bar vs. B2B (`boteco_cozinha_central` + `boteco_b2b`)

> **🤖 CHECKPOINT ANTIGRAVITY — PERGUNTE AO USUÁRIO ANTES DE INICIAR A ETAPA 17:**
> *"Na Etapa 17 vamos evoluir a produção de congelados (`boteco_cozinha_central` e `boteco_b2b`). Confirme quais recursos deseja ativar:*
> *1. `boteco_flag_capacidade_finita_congelados`: Limitar o Plano de Produção pela capacidade diária máxima de produção por item e da cozinha.*
> *2. `boteco_flag_controle_volume_freezer`: Controlar a capacidade em Litros dos freezers e travar ordens que ultrapassem o espaço livre.*
> *3. `boteco_flag_reserva_estoque_bar_b2b`: Proteger a Reserva Exclusiva do Bar para que vendas de revenda B2B não deixem o bar sem produto à noite.*
> *4. `boteco_flag_explosao_insumos_fator_coccao`: Calcular Fator de Correção/Cocção na Ficha Técnica e alertar no Plano de Produção quais matérias-primas faltam no estoque."*

### 17.1. Alterações de Código
* Atualizar `addons/boteco_cozinha_central/models/stock_warehouse.py`, `product_template.py`, `mrp_bom.py`, `wizard/boteco_plano_producao.py` e `addons/boteco_b2b/models/sale_order.py` conforme especificado nos blocos de código da Parte 1.3, sempre respeitando as flags da Central de Recursos.

---

## ETAPA 18: Inteligência de Compras — Leitura de Instagram, Imagem/PDF de Orçamento e Radar de Preços (`boteco_estoque` + `boteco_painel`)

> **🤖 CHECKPOINT ANTIGRAVITY — PERGUNTE AO USUÁRIO ANTES DE INICIAR A ETAPA 18:**
> *"Na Etapa 18 vamos implementar o motor de Compras Inteligentes e Radar de Preços (`boteco_estoque` e `boteco_painel`). Confirme quais funções deseja habilitar:*
> *1. `boteco_flag_leitor_orcamento_pdf_imagem`: Wizard para enviar PDF ou Foto de orçamento de fornecedor e extrair itens/preços automaticamente.*
> *2. `boteco_flag_monitor_instagram_fornecedores`: Monitoramento automático de posts de ofertas no Instagram (`@perfil`) dos fornecedores.*
> *3. `boteco_flag_radar_precos_oportunidade`: Histórico de preços (60d/90d), detecção automática de preços interessantes ($\ge 10\%$ abaixo da média), cálculo de economia no lote de congelados e seleção automática do fornecedor mais barato na Lista de Compras."*

### 18.1. Alterações de Código
* Criar `addons/boteco_estoque/models/res_partner.py`, `addons/boteco_estoque/models/boteco_historico_preco.py`, `addons/boteco_estoque/wizard/boteco_importar_orcamento.py` e views XML correspondentes.
* Integrar com `boteco_nfe_importacao.py`, `boteco_lista_compras.py` e exibir o card de **Oportunidades de Compra para Congelados** no Painel do Dono (`addons/boteco_painel/models/boteco_painel.py`).

---

## ETAPAS 19 A 23: MÓDULOS AVANÇADOS OPCIONAIS DO PRD MASTER (PERGUNTAR UM POR UM AO USUÁRIO)

### ETAPA 19: Recursos Avançados de Frente de Caixa — Fichas Avulsas, Balança EAN-13, Meio a Meio e Atalhos F1-F12 (`boteco_pos`)
> **🤖 CHECKPOINT ANTIGRAVITY — PERGUNTE AO USUÁRIO ANTES DE INICIAR A ETAPA 19:**
> *"Deseja implementar agora algum dos recursos avançados de PDV do Módulo 3 do PRD Master?*
> *- `boteco_flag_pdv_atalhos_f1_f12`: Atalhos de teclado F1 a F12 no caixa + edição da forma de pagamento pós-venda.*
> *- `boteco_flag_pdv_fichas_avulsas`: Impressão de fichas individuais destacáveis por item com código de barras antifalsificação.*
> *- `boteco_flag_pdv_balanca_ean13`: Decodificação de etiqueta de balança (prefixo 2) e montagem de itens fracionados (meio a meio)."*

### ETAPA 20: Validador de Saída na Portaria e Tags Rápidas / Smart POS para Garçom (`boteco_pos`)
> **🤖 CHECKPOINT ANTIGRAVITY — PERGUNTE AO USUÁRIO ANTES DE INICIAR A ETAPA 20:**
> *"Deseja implementar agora os recursos de Portaria e Mobilidade dos Módulos 4 e 5 do PRD Master?*
> *- `boteco_flag_portaria_validador_saida`: Tela `/boteco/portaria` para o segurança bipar a comanda na saída e ver tela VERDE (Paga) ou VERMELHA (Pendente).*
> *- `boteco_flag_garcom_tags_rapidas`: Botões de observação de 1 toque (`[Sem Cebola]`, `[Ao Ponto]`, `[Gelo e Limão]`) e integração DeepLink para maquininhas Smart POS."*

### ETAPA 21: KDS Avançado — Totalizador de Grelha, Sincronia de Praças (Pacing) e Bump Bar USB (`boteco_kds`)
> **🤖 CHECKPOINT ANTIGRAVITY — PERGUNTE AO USUÁRIO ANTES DE INICIAR A ETAPA 21:**
> *"Deseja implementar agora as melhorias avançadas do Monitor KDS (Módulo 9.2 do PRD Master) controladas pela flag `boteco_flag_kds_totalizador_pacing`?*
> *- Painel lateral Totalizador de Grelha (soma todos os itens iguais abertos na fila).*
> *- Pacing de preparo (sincroniza o início do prato rápido com o prato demorado da mesma mesa).*
> *- Baixa rápida por teclado numérico USB (Bump Bar)."*

### ETAPA 22: Agente de IA no WhatsApp, Régua de CRM (Clientes Sumidos) e Roteirização de Delivery (`boteco_cardapio` + `boteco_pos`)
> **🤖 CHECKPOINT ANTIGRAVITY — PERGUNTE AO USUÁRIO ANTES DE INICIAR A ETAPA 22:**
> *"Deseja implementar agora os recursos de Canais Próprios e Delivery (Módulos 10 e 11 do PRD Master) controlados pela flag `boteco_flag_crm_whatsapp_ia`?*
> *- Endpoint de integração para Bot de WhatsApp IA lançar pedidos direto no PDV.*
> *- Relatório e régua automática de 'Clientes que Sumiram' (inativos há mais de 21 dias) e Aniversariantes.*
> *- Controle de Taxa de Entrega por Bairro e Fechamento de Turno de Motoboys."*

### ETAPA 23: Pix Dinâmico com Baixa Automática, Rateio de Gorjeta (10%) e Contingência Fiscal (`boteco_painel` + `boteco_fiscal_export`)
> **🤖 CHECKPOINT ANTIGRAVITY — PERGUNTE AO USUÁRIO ANTES DE INICIAR A ETAPA 23:**
> *"Deseja implementar agora os recursos Financeiros e Fiscais avançados (Módulos 13 e 14 do PRD Master) controlados pela flag `boteco_flag_financeiro_pix_rateio`?*
> *- Webhook de confirmação automática de Pix Dinâmico na comanda.*
> *- Relatório de Rateio configurável da Taxa de Serviço (ex.: % Garçom, % Cozinha/Bar, % Casa).*
> *- Exportação automática do pacote mensal ZIP para o e-mail do Contador."*

---

## ETAPA 24: População de Dados de Exemplo (`scripts/dados_exemplo.py`) e Verificação de Telas
* Atualizar `scripts/dados_exemplo.py` para configurar a Central de Recursos, criar os produtos com taxonomia de consumo e regras de utensílios, configurar os congelados com reserva do bar e volume de freezer, e inserir o histórico de preços com uma oferta ativa de matéria-prima.

## ETAPA 25: Suíte Completa de Testes Automatizados End-to-End (`./scripts/testar.sh`)
* Executar e validar todos os testes automatizados cobrindo:
  1. Funcionamento da **Central de Recursos (Liga/Desliga)**: testar que desligar uma flag na tela da empresa desativa imediatamente aquele bloqueio ou regra sem quebrar o fluxo padrão.
  2. Ocupação padrão na abertura da mesa e bloqueio de 10 pratos para 2 clientes (`boteco_autoatendimento`).
  3. Resolução rápida pelo alerta do garçom/caixa (ajustando clientes de 2 para 10 ou corrigindo item de 10 para 1).
  4. Impressão de `[N] COPOS` apenas na 1ª cerveja, delta de novos clientes e alerta de Vinho sem Água (`boteco_kds`).
  5. Nivelamento do Plano de Produção pela capacidade diária e espaço livre no freezer + bloqueio de venda B2B sobre a reserva exclusiva do Bar (`boteco_cozinha_central` e `boteco_b2b`).
  6. Extração de orçamento PDF/Imagem/Instagram e detecção de `preco_interessante` com cálculo de economia para produção de congelados (`boteco_estoque` e `boteco_painel`).