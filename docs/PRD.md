# PRD – Sistema Boteco Raiz

Oct 6, 2026 · @ricardo

## 1. Visão geral

O sistema controla o Boteco Raiz inteiro num servidor local: salão, caixa, bar, chapa, pedidos por tablet e QR Code, estoque, cozinha central, venda de tira-gosto a outros bares e administração. A base é o Odoo Community (gratuito, licença LGPL), que já traz PDV de restaurante, cardápio por QR e tablet, estoque, compras, produção e vendas. O Claude, no Google Antigravity, instala o Odoo, configura o que já existe e programa só o que falta, em módulos próprios, uma etapa por vez. O URY serve de modelo para a tela de cozinha e o fluxo de restaurante.

**Objetivo de negócio (do plano):** atender cerca de 80 lugares com equipe enxuta (1 chapeiro, 2 garçons, 1 barman/caixa), entregar comida em até 30 minutos e controlar CMV, lotes e vendas para que o bar seja a vitrine da cozinha central e da assessoria a outros bares.

**Está no escopo:**

- Pedido pelo cliente (tablet na mesa e QR no celular) e pelo garçom
- Roteamento automático do pedido para o bar e para a chapa (impressora e tela)
- Caixa, contas, pagamentos e fechamento do dia
- Estoque, compras, ficha técnica e CMV
- Produção da cozinha central com lote, validade e etiqueta
- Venda B2B de tira-gosto e cobrança da assessoria
- Financeiro simples e painel do dono
- **Controle fiscal para emissão posterior:** o sistema não emite nota. Ele guarda tudo o que a nota precisa, marca cada venda como pendente e exporta para outro sistema emitir depois

**Fica fora desta versão:** emissão de NFC-e ou NF-e, integração com maquininha (TEF), delivery por aplicativo, folha de pagamento e contabilidade. Estão em Melhorias futuras.

## 2. Verificação de lacunas

Antes de escrever as etapas, cruzei o pedido com o plano de negócios e com a operação real de um boteco. Estes itens não tinham sido citados e entraram no PRD, porque sem eles o sistema trava na primeira noite ou abre brecha para perda de dinheiro.

| Item que faltava | Por que importa | Onde entrou |
| --- | --- | --- |
| Taxa de serviço (10%) e couvert artístico | O plano cobra couvert; a taxa precisa ser opcional por conta | Etapa 2 |
| Dividir conta e pagar em várias formas | Grupo de 4 pessoas raramente paga junto | Etapa 2 |
| Abertura, sangria, reforço e fechamento de caixa | Sem isso não dá para conferir dinheiro no fim da noite | Etapa 2 |
| Cancelamento de item só com senha do gerente e motivo | Principal porta de desvio em bar | Etapa 2 |
| Cortesia, consumo de funcionário e perda | Sai do estoque sem virar venda; precisa aparecer no CMV | Etapas 2 e 5 |
| Preço de happy hour automático (17h às 21h) | Estratégia central do plano | Etapa 1 |
| Oferta relâmpago com quantidade limitada | Cardápio dinâmico do plano; some do tablet quando esgota | Etapa 1 |
| Cronômetro de preparo e alerta acima de 30 minutos | Meta de entrega do plano | Etapa 3 |
| Chamar garçom e pedir a conta pelo tablet | Garçom "passador" precisa de aviso, não de ronda | Etapa 4 |
| Segurança do QR Code | Sem proteção, alguém de fora pede bebida na conta de uma mesa | Etapa 4 |
| Aviso de venda de álcool só para maiores de 18 | O tablet não confere idade; o primeiro pedido de álcool por mesa passa pelo garçom | Etapa 4 |
| Etiqueta obrigatória do saco a vácuo (produto, fabricação, validade, lote) | Exigência da Vigilância citada no plano | Etapa 6 |
| Rastreio de lote até o cliente B2B | Necessário para recolher produto com problema | Etapas 6 e 7 |
| Bar e cozinha central como empresas (CNPJs) separadas | Decisão pendente do contador; o sistema precisa aceitar as duas formas | Etapa 0 |
| Preparado para vários bares desde o início | A assessoria vai instalar o sistema em outros bares | Etapa 0 |
| Cobrança da implantação (R$ 3.500) e mensalidade (R$ 450) da assessoria | Receita prevista no plano | Etapa 7 |
| Fechamento do dia com relatório (vendas, formas de pagamento, cancelamentos) | Conferência diária do dono | Etapa 8 |
| Registro de auditoria (quem fez o quê e quando) | Investigar diferenças de caixa e estoque | Etapa 0 |
| Funcionar sem internet e plano para queda do servidor | Operação noturna não pode parar | Requisitos não funcionais |
| Backup automático | Um HD queimado não pode apagar o negócio | Etapa 10 |
| LGPD para telefone e CPF de cliente | Obrigação legal ao guardar dados pessoais | Requisitos não funcionais |
| Dados fiscais completos no cadastro (NCM, CFOP, CST/CSOSN) | Sem eles a emissão posterior não funciona | Etapas 1 e 9 |

## 3. Perfis de usuário e permissões

Cada pessoa entra com um PIN de 4 a 6 dígitos e cai direto na tela do seu trabalho. Nenhum perfil vê menus que não usa.

| Perfil | Aparelho | Tela inicial | Pode | Não pode |
| --- | --- | --- | --- | --- |
| Cliente (sem login) | Tablet da mesa ou celular via QR | Cardápio da mesa | Pedir, ver a conta, chamar garçom, pedir a conta | Ver outras mesas, cancelar item enviado |
| Garçom | Celular ou tablet | Mapa de mesas | Abrir mesa, lançar e entregar itens, transferir item, aprovar pedido de QR | Cancelar item enviado, dar desconto, fechar caixa |
| Barman/caixa | PC ou tablet no balcão | Fila do bar + caixa | Tudo do garçom, receber pagamento, sangria e reforço | Cancelar sem gerente, ver relatórios financeiros |
| Chapeiro | Tela na chapa | Fila da chapa | Marcar "preparando" e "pronto" | Qualquer coisa fora da fila |
| Gerente | Qualquer | Painel do turno | Cancelar com motivo, desconto, cortesia, abrir e fechar caixa, ajustar estoque | Mudar configuração do sistema e usuários |
| Cozinheiro (cozinha central) | Tablet na cozinha central | Ordens de produção do dia | Produzir lote, imprimir etiqueta, registrar perda | Preços, vendas, financeiro |
| Comercial B2B | Qualquer | Pedidos de outros bares | Cadastrar cliente B2B, lançar pedido, marcar entrega | Financeiro geral |
| Dono/administrador | Qualquer | Painel do dono | Tudo, inclusive usuários, preços, fiscal e configurações | — |

As permissões são configuráveis por perfil numa tela simples de liga/desliga. Toda ação sensível (cancelar, desconto, cortesia, ajuste de estoque, sangria) pede o PIN do gerente na hora e fica no registro de auditoria.

## 4. Princípios de facilidade de uso

"Extremamente fácil" vira regra verificável. Toda tela entregue em qualquer etapa precisa cumprir esta lista, e o agente deve conferi-la antes de dar a etapa por pronta.

1. **Uma tela, um trabalho.** Cada perfil abre direto na sua tarefa principal. No máximo 2 níveis de menu.
2. **Até 3 toques para a ação principal.** Pedir um item no tablet: tocar no item, tocar em "Adicionar", tocar em "Enviar pedido".
3. **Botões grandes.** Alvo mínimo de 48 x 48 px; 64 px nas telas de cozinha e chapa (mão molhada, de luva).
4. **Fotos e cores no lugar de texto.** Cardápio com foto; status por cor fixa: cinza = aguardando, amarelo = preparando, verde = pronto, vermelho = atrasado.
5. **Linguagem de boteco, em português.** "Mandar pra cozinha", "Fechar a conta". Nunca termos técnicos como "ordem de venda" ou "SKU" nas telas de operação.
6. **Nada se perde.** Rascunho do pedido salvo a cada toque; se o tablet travar ou a rede cair, o pedido volta.
7. **Desfazer em vez de confirmar.** Ações comuns não pedem "Tem certeza?"; mostram "Desfazer" por 5 segundos. Só ações irreversíveis pedem confirmação.
8. **Erros que dizem o que fazer.** "Impressora da chapa desligada. Ligue e toque em Tentar de novo." e não "Erro 500".
9. **Modo escuro nas telas de produção** e contraste alto para ambiente noturno.
10. **Primeiro acesso guiado.** Cada perfil vê um tour de 3 telas na primeira vez e um botão "?" com vídeo curto ou passo a passo.
11. **Teste com usuário real.** Ao fim de cada etapa com tela, uma pessoa que não participou do projeto precisa concluir a tarefa principal sem ajuda em até 1 minuto.

## 5. Arquitetura, stack e regras para o agente

**Arquitetura:** um mini PC Linux no bar roda o Odoo Community e o PostgreSQL em Docker. Tablets, celulares, PCs e telas de cozinha acessam pelo navegador na rede Wi-Fi interna. A cozinha central acessa o mesmo Odoo por VPN (WireGuard). A internet só é necessária para backup e acesso remoto do dono.

**Base: baixar e usar o Odoo Community.**

- Repositório: [github.com/odoo/odoo](https://github.com/odoo/odoo), versão 18.0, pela imagem oficial `odoo:18` no Docker.
- **Por que 18.0 e não 19.0:** a localização brasileira da comunidade (OCA/l10n-brazil) avisa que a branch 19.0 é só de transição e recomenda a 18.0 para projetos novos (ou esperar a 20.0, prevista para meados de 2027). Na 18.0 ela tem 53 módulos, contra 20 na 19.0; o repositório OCA/pos tem 28 módulos na 18.0 e 4 na 19.0. Tudo o que o bar usa do Odoo (PDV de restaurante, autoatendimento por QR e tablet, estoque, compras, receitas, l10n\_br e impressão direta em Epson ePOS) existe na 18.0 Community.
- Licença LGPL-3: os módulos que vocês criarem podem continuar fechados e ser vendidos na assessoria.
- **Nunca alterar o código do Odoo.** Toda mudança fica em módulos próprios na pasta `addons/` do projeto, para atualizar o Odoo sem perder nada.
- Usar só a versão Community. Nada que dependa da versão paga (Enterprise), como a tela de cozinha oficial ou a caixinha IoT.
- **Repositórios da comunidade (OCA), branch 18.0:** github.com/OCA/pos (melhorias de PDV, por exemplo fechamento de caixa cego, restrição de usuário por PDV, validade de lote no PDV, editar e remover linha) e github.com/OCA/l10n-brazil (fiscal completo). Consultar antes de programar algo do zero. Módulo da OCA com licença LGPL pode ser instalado como está; módulo AGPL serve só de estudo, sem copiar código para os módulos boteco\_ (a licença de cada módulo está no \_\_manifest\_\_.py).
- **Referência de uso em celular e tablet:** github.com/mobo-open-source/mobo\_pos (Apache 2.0). É um app Flutter que abre o próprio PDV do Odoo dentro dele, então serve de ideia para login rápido, troca de sessão e de empresa, não como modelo de telas. As telas continuam no navegador, em OWL.

**Módulos nativos do Odoo a ativar:**

| Módulo do Odoo | Para quê |
| --- | --- |
| Ponto de Venda + Restaurante (`point_of_sale`, `pos_restaurant`) | Mapa de mesas, comandas, dividir conta, pagamentos, caixa, impressoras de pedido |
| Autoatendimento (`pos_self_order`) | Cardápio por QR no celular e modo quiosque no tablet da mesa |
| Estoque (`stock`) com lotes e validade | Estoque do bar e da cozinha central, lotes, transferências |
| Compras (`purchase`) | Pedidos e recebimento de fornecedores |
| Fabricação (`mrp`) | Receitas, ordens de produção, consumo de insumos na cozinha central |
| Vendas (`sale`) e Faturamento (`account`) | Pedidos B2B, contas a receber e a pagar |
| Localização Brasil (`l10n_br`) | CNPJ, CPF, plano de contas e campos fiscais básicos |
| Multiempresa | Bar e cozinha central como empresas ou unidades separadas |

**Módulos próprios a criar (prefixo `boteco_`):**

| Módulo | O que faz | Etapa |
| --- | --- | --- |
| `boteco_base` | Perfis simplificados, menus escondidos por perfil, login por PIN, auditoria, tradução de termos para linguagem de boteco | 0 |
| `boteco_cardapio` | Happy hour por horário, oferta relâmpago com limite, botão "Acabou", marcação +18, dados fiscais obrigatórios | 1 |
| `boteco_pos` | Couvert, taxa de serviço, cancelamento com PIN do gerente, cortesia, consumo de funcionário, fechamento cego de caixa | 2 |
| `boteco_kds` | Tela de cozinha e bar (KDS) com cronômetro e alertas, inspirada no Mosaic do URY | 3 |
| `boteco_autoatendimento` | Chamar garçom, pedir a conta, aprovação do primeiro pedido por QR, aviso +18, "Pedir de novo" | 4 |
| `boteco_cozinha_central` | Tela simples de produção, etiqueta do saco a vácuo, temperatura dos freezers, rastreio de lote | 6 |
| `boteco_b2b` | Pedido recorrente, romaneio, contratos e mensalidades da assessoria | 7 |
| `boteco_painel` | Painel do dono e DRE por frente | 8 |
| `boteco_fiscal_export` | Controle de notas pendentes, exportação e importação do retorno | 9 |

**URY como modelo, sem copiar código.** O [URY](https://github.com/ury-erp/ury) é a referência de telas e fluxos de restaurante: tela de cozinha (Mosaic), app do garçom, pedido por QR, ficha técnica. Ele tem licença AGPL-3; copiar código dele obrigaria a abrir o código dos módulos de vocês. O agente pode estudar o repositório e reproduzir as ideias, mas escreve o código do zero.

**Tecnologia dos módulos próprios:** Python e XML do Odoo no servidor; OWL (o framework de telas do Odoo) nas telas do PDV, autoatendimento e KDS; relatórios em QWeb; impressão de etiqueta em ZPL ou TSPL.

**Decisões de base:**

- Bar e cozinha central configurados como duas empresas no Odoo, ou uma empresa com dois armazéns, conforme a decisão do contador.
- Nada é apagado: registros ficam arquivados ou cancelados, com motivo e autor.
- Termos do Odoo traduzidos para linguagem de boteco nos menus de operação ("Pedido" em vez de "Ordem de venda").
- Fuso de Brasília; o "dia de operação" vira às 6h (sessão do PDV aberta até o fechamento).
- Impressoras de pedido: preferir modelos Epson com ePOS (o PDV do Odoo imprime direto neles, sem caixinha IoT). Confirmar na Etapa 0; se usar outra marca, o `boteco_base` inclui um pequeno serviço de impressão ESC/POS pela rede.

**Regras de trabalho para o Claude no Antigravity:**

1. Antes de programar qualquer coisa, verificar se o Odoo já faz por configuração. Programar só o que falta.
2. Trabalhar uma etapa por vez, na ordem deste documento.
3. Antes de cada etapa, escrever um plano curto: o que é configuração nativa, o que vira módulo próprio, telas, testes. Esperar aprovação.
4. Cada etapa termina com: módulos instaláveis, dados de exemplo, testes do Odoo passando, a lista da seção 4 conferida e um `docs/etapa-N.md` explicando como testar.
5. Os critérios de aceite são a definição de pronto. Se um critério não puder ser atendido, parar e perguntar.
6. Git com um commit por funcionalidade e uma tag por etapa (`etapa-0`, `etapa-1`...). Senhas só no `.env`.
7. Antes de programar uma solução do zero, procurar se a OCA (OCA/pos, OCA/l10n-brazil, branch 18.0) já resolve. Se o módulo for LGPL, propor instalá-lo; se for AGPL, estudar a abordagem e escrever o código próprio, sem copiar. Registrar no plano da etapa o que foi consultado.

## 6. Modelo de dados principal

A maior parte dos dados já existe no Odoo. O agente estende os modelos nativos (herança `_inherit`) e só cria modelos novos onde o Odoo não tem nada parecido.

| Conceito do boteco | Modelo do Odoo | O que acrescentar |
| --- | --- | --- |
| Empresa, unidade | `res.company`, `stock.warehouse` | Tipo de unidade (bar, cozinha central) |
| Usuário e perfil | `res.users`, `res.groups`, `hr.employee` (PIN no PDV) | Perfis simplificados da seção 3 |
| Auditoria | `mail.thread` (histórico) | Modelo `boteco.auditoria` para ações do PDV (cancelar, desconto, cortesia) |
| Produto e categoria | `product.template`, `pos.category` | Preço happy hour, +18, "Acabou", setor de produção, tempo de preparo |
| Dados fiscais do produto | `product.template` + `l10n_br` | NCM, CEST, CFOP, CST/CSOSN, origem obrigatórios |
| Adicionais | `product.attribute` e combos do PDV | Nada, só configurar |
| Promoção | `product.pricelist` com regras por horário | Modelo `boteco.oferta.relampago` (limite e vendidos) |
| Mesa e QR | `restaurant.floor`, `restaurant.table` | Código de sessão da mesa, status "chamou garçom" e "pediu a conta" |
| Conta e itens | `pos.order`, `pos.order.line` | Origem (tablet, QR, garçom), horários de cada status, motivo de cancelamento, cortesia |
| Pagamento e caixa | `pos.payment`, `pos.session` | Contagem cega, sangria e reforço com motivo |
| Insumo, ficha técnica | `product.product`, `mrp.bom` | Nada, só configurar (BoM tipo "kit" para baixa na venda) |
| Estoque e perdas | `stock.move`, `stock.scrap`, `stock.quant` | Motivos de perda do boteco |
| Compras | `purchase.order`, importação de XML de NF-e | Leitor de XML do fornecedor, se o nativo não atender |
| Produção e lote | `mrp.production`, `stock.lot` (validade) | Etiqueta do saco a vácuo, registro de temperatura |
| Cliente e pedido B2B | `res.partner`, `sale.order` | Preço por kg por cliente (lista de preço), pedido recorrente |
| Assessoria | `sale.order` + faturas | Modelo `boteco.contrato.assessoria` gerando mensalidades |
| Financeiro | `account.move`, `account.payment` | Categorias por frente (bar, B2B, assessoria) |
| Registro fiscal | Novo modelo `boteco.fiscal.registro` | Status (pendente, exportado, emitido, não emitir), lote de exportação, número e chave |

## 7. Etapas de desenvolvimento

São 11 etapas. As etapas 0 a 4 formam o mínimo para abrir o bar; as demais podem entrar com o bar já funcionando.

### Etapa 0. Fundação

**Objetivo:** projeto rodando no mini PC com login por PIN, perfis e auditoria.

**No Odoo:** instalar o Odoo Community 18 e os módulos nativos. **Programar:** `boteco_base`.

**Entregas:**

- Projeto com `docker-compose.yml` (imagem oficial `odoo:18` + PostgreSQL 16), pasta `addons/` para os módulos próprios, `.env.example` e script `./instalar.sh` que sobe tudo com um comando
- Banco criado em português do Brasil, fuso de São Paulo, moeda real, localização `l10n_br`
- Módulos nativos da seção 5 instalados e configurados: empresa(s), armazéns do bar e da cozinha central, PDV do bar com plantas de mesas
- Teste de impressão de pedido numa impressora real (Epson ePOS) antes de seguir; registrar o resultado em `docs/etapa-0.md`
- `boteco_base`: perfis da seção 3 como grupos do Odoo, menus escondidos por perfil, tela inicial por perfil, login por PIN no PDV, registro de auditoria
- Página de saúde do sistema (banco, impressoras, espaço em disco, último backup)

**Critérios de aceite:**

- [ ] Num mini PC limpo, `./instalar.sh` deixa o sistema acessível em `http://boteco.local` em até 10 minutos
- [ ] Um garçom entra com PIN e vê só o que o perfil dele permite
- [ ] Alterar um preço grava quem, quando, valor antigo e novo
- [ ] Botão "Imprimir teste" imprime numa térmica 80 mm pela rede

### Etapa 1. Cadastros e cardápio

**Objetivo:** cardápio completo, com fotos, preços, promoções, mesas e dados fiscais.

**No Odoo (nativo):** produtos, categorias do PDV com foto, atributos e combos, listas de preço, plantas de mesas e QR por mesa do autoatendimento. **Programar (`boteco_cardapio`):** happy hour automático, oferta relâmpago com limite, botão "Acabou", +18, validação dos dados fiscais, cadastro rápido de produto numa tela só.

**Entregas:**

- Categorias e produtos com foto (upload com recorte automático quadrado), descrição curta, preço e setor de produção
- Adicionais (ex.: "ponto da carne", "molho extra +R$ 3") com obrigatório/opcional
- Marcação +18 nas bebidas alcoólicas
- Happy hour: preço alternativo por produto, dias e horário (padrão: quarta a domingo, 17h às 21h); troca automática no tablet e no caixa
- Oferta relâmpago: produto, preço, quantidade limite e horário; um botão "Lançar agora" coloca a oferta no topo do tablet; some sozinha ao esgotar
- Botão "Acabou" no produto, que tira do tablet na hora sem apagar
- Mesas: número, área (salão, área aberta), lugares; geração do QR Code de cada mesa em PDF para imprimir
- Dados fiscais do produto (ver seção 6), com aviso amarelo em produto sem NCM ou CFOP
- Importar e exportar cardápio por planilha

**Critérios de aceite:**

- [ ] Às 20h59 o tablet mostra preço de happy hour; às 21h00 mostra o preço normal, sem recarregar
- [ ] Oferta relâmpago de 20 unidades some do tablet ao vender a 20ª
- [ ] Tela de cadastro de produto preenchida em menos de 1 minuto por quem nunca usou
- [ ] Relatório "Produtos sem dados fiscais" lista todos os pendentes

### Etapa 2. Salão, contas e caixa

**Objetivo:** operar uma noite inteira só com garçom e caixa (sem tablet ainda).

**No Odoo (nativo):** mapa de mesas, transferir e juntar mesas, dividir conta, várias formas de pagamento, abertura e fechamento de sessão do caixa, entrada e saída de dinheiro. **Programar (`boteco_pos`):** couvert por pessoa, taxa de serviço removível, cancelamento e desconto com PIN do gerente e motivo, cortesia, consumo de funcionário, contagem cega no fechamento, cores de mesa por situação.

**Entregas:**

- Mapa de mesas com cor por situação: livre, ocupada, pediu a conta, esperando pagamento, atrasada; tempo desde o último pedido
- Abrir mesa com número de pessoas; lançar itens com busca, categoria e adicionais; observação livre
- Comanda avulsa (balcão, sem mesa)
- Transferir item ou mesa inteira; juntar mesas
- Couvert artístico por pessoa, ligado nos dias de música
- Taxa de serviço de 10% sugerida, que o caixa pode tirar com um toque (fica registrado)
- Dividir conta: por pessoa em partes iguais, por item ou por valor
- Pagamento em várias formas e várias pessoas; cálculo de troco; CPF na nota opcional (para a emissão posterior)
- Pré-conta impressa e por QR na mesa
- Cancelamento de item: antes de ir para produção, livre; depois, só com PIN do gerente e motivo da lista (erro do garçom, desistência, problema no produto)
- Desconto e cortesia com PIN do gerente e motivo
- Consumo de funcionário lançado como conta especial a preço de custo ou zero
- Caixa: abrir com valor inicial; sangria e reforço; fechar com contagem "cega" (o operador digita o que contou antes de ver o esperado); impressão do resumo
- Fechamento do dia: não deixa fechar com mesa aberta

**Critérios de aceite:**

- [ ] Conta de 4 pessoas dividida em 3 PIX e 1 cartão fecha com saldo zero
- [ ] Item cancelado após envio sem PIN de gerente é bloqueado
- [ ] Fechamento de caixa mostra a diferença entre contado e esperado por forma de pagamento
- [ ] Garçom abre mesa e lança 3 itens em menos de 20 segundos

### Etapa 3. Produção no bar e na chapa

**Objetivo:** cada pedido chega sozinho ao lugar certo, e todos veem o andamento.

**No Odoo (nativo):** impressoras de pedido por categoria no PDV de restaurante (bebida no bar, porção na chapa). **Programar (`boteco_kds`):** a tela de cozinha, porque a do Odoo só existe na versão paga. Modelo de referência: o Mosaic do [URY](https://github.com/ury-erp/ury) (cartões por pedido, fila em tempo real, toque para mudar status). Estudar as telas e o fluxo dele e escrever o código do zero em OWL, usando o barramento em tempo real do próprio Odoo.

**Entregas:**

- Roteamento por setor: bebidas para o bar, porções para a chapa, cada um na sua impressora e na sua tela
- Ticket impresso grande e legível: mesa, hora, itens, adicionais, observações em destaque, origem (tablet, QR, garçom)
- Tela de produção (KDS): cartões por pedido, toque para "preparando" e "pronto"; som ao chegar pedido; cronômetro em cada cartão
- Cor do cartão pelo tempo: verde até 10 min, amarelo até 20, vermelho acima de 20; alerta ao gerente acima de 30
- Aviso ao garçom quando o item fica pronto (no celular do garçom e numa tela de "prontos para entregar")
- Garçom marca "entregue"
- Reimpressão de ticket e fila de impressão: se a impressora cair, os tickets esperam e saem quando ela voltar, com aviso na tela
- Relatório de tempos médios por produto e por hora da noite

**Critérios de aceite:**

- [ ] Pedido com cerveja e porção imprime em 2 impressoras diferentes em até 2 segundos
- [ ] Desligar e religar a impressora não perde nenhum ticket
- [ ] Pedido parado há 31 minutos aparece em vermelho e gera alerta ao gerente
- [ ] Tela da chapa funciona sem teclado e sem mouse

### Etapa 4. Tablet na mesa e QR Code

**Objetivo:** o cliente pede sozinho; o garçom só entrega e atende.

**No Odoo (nativo):** `pos_self_order` com QR por mesa (celular) e modo quiosque (tablet), cardápio com fotos, carrinho e envio do pedido para a produção. **Programar (`boteco_autoatendimento`):** chamar garçom, pedir a conta, conta parcial com status de cada item, aprovação do primeiro pedido por QR, código de sessão da mesa, aviso +18, "Pedir de novo", tela de descanso com ofertas. Referência de fluxo: pedido por QR do URY.

**Entregas – tablet da mesa:**

- Modo quiosque: o tablet fica preso ao cardápio da mesa; só sai com PIN do gerente
- Tela inicial com destaques (oferta relâmpago, happy hour) e categorias com foto
- Pedido em 3 toques; carrinho com edição; "Enviar pedido" manda para a produção
- "Minha conta": itens, status de cada um (na fila, preparando, a caminho), total parcial, taxa e couvert
- Botões fixos "Chamar garçom" e "Pedir a conta", que avisam o garçom e mudam a cor da mesa no mapa
- Tablet volta para a tela de boas-vindas quando a conta fecha e limpa o histórico
- Tela "descanso" com ofertas depois de 2 minutos parado

**Entregas – QR Code no celular:**

- QR fixo da mesa abre o cardápio no navegador, sem instalar nada e sem cadastro
- Funciona só com a mesa aberta pelo garçom; com a mesa fechada mostra apenas o cardápio para consulta
- Segurança: cada abertura de mesa gera um código novo de sessão; o primeiro pedido de cada celular precisa de aprovação do garçom (um toque); limite de valor por pedido via QR configurável
- Atalho "Pedir de novo" mostra as bebidas já pedidas na mesa para repetir com 1 toque (re-compra rápida do plano)

**Regras comuns:**

- Primeiro item com álcool de cada mesa mostra o aviso "Venda proibida para menores de 18 anos" e vai para o garçom confirmar
- Se a rede cair, o pedido fica salvo no aparelho e é enviado quando a rede voltar, com aviso claro ao cliente
- O cardápio carrega em menos de 2 segundos com fotos otimizadas

**Critérios de aceite:**

- [ ] Cliente sem instrução pede 2 cervejas e 1 porção pelo tablet em menos de 30 segundos
- [ ] Celular fora da rede do bar com foto antiga do QR não consegue pedir
- [ ] "Pedir a conta" muda a mesa para roxo no mapa e avisa o garçom em até 2 segundos
- [ ] Desligar o Wi-Fi no meio do pedido não perde o carrinho

### Etapa 5. Estoque e compras do bar

**Objetivo:** saber o que tem, o que falta e quanto custou cada venda.

**No Odoo (nativo):** estoque, ficha técnica como lista de materiais do tipo "kit" (baixa os insumos na venda do PDV), custo médio, compras, inventário, sucata (perdas), regras de estoque mínimo, transferência entre armazéns. **Programar:** relatório de CMV por noite, leitor do XML da nota do fornecedor se o nativo não atender, envio da lista de compras por WhatsApp, telas simplificadas de contagem pelo celular.

**Entregas:**

- Cadastro de insumos com unidade e estoque mínimo
- Ficha técnica de venda: cada produto baixa seus insumos (ex.: porção de bolinho = 12 unidades do lote congelado + 30 g de molho)
- Baixa automática de estoque a cada item vendido; estorno no cancelamento
- Entrada de compra: fornecedor, itens, quantidade, custo; leitura do XML da nota do fornecedor para preencher sozinho
- Custo médio ponderado atualizado a cada entrada
- Registro de perda (quebra, vencido, erro de preparo) com motivo; cortesia e consumo interno já vêm da etapa 2
- Contagem de estoque (inventário) pelo celular, com diferença e ajuste aprovado pelo gerente
- Lista de compras sugerida: tudo abaixo do mínimo, agrupado por fornecedor, com envio por WhatsApp (link pronto)
- Recebimento de transferências vindas da cozinha central (etapa 6)
- CMV por produto, por categoria e por noite

**Critérios de aceite:**

- [ ] Vender 10 porções baixa exatamente os insumos da ficha técnica
- [ ] Importar um XML de nota de fornecedor cria a entrada sem digitação
- [ ] Relatório de CMV da noite bate com a soma dos custos dos itens vendidos

### Etapa 6. Cozinha central

**Objetivo:** produzir em lotes rastreáveis, etiquetar e abastecer o bar e os clientes B2B.

**No Odoo (nativo):** Fabricação (receitas, ordens de produção, consumo de insumos), lotes com data de validade, saída pelo lote que vence primeiro (FEFO), rastreabilidade do lote. **Programar (`boteco_cozinha_central`):** tela de produção com botões grandes (Iniciar, Pesar, Finalizar), etiqueta ZPL do saco a vácuo, plano de produção sugerido, registro de temperatura, bloqueio de lote vencido.

**Entregas:**

- Receitas de produção: insumos crus, rendimento, perda esperada, validade em dias (congelado e resfriado), modo de preparo e fotos
- Plano de produção: sugestão do que produzir com base no estoque do bar, pedidos B2B e média de venda por dia da semana
- Ordem de produção em tela grande: "Iniciar", "Pesar" (digitar o peso real), "Finalizar"
- Ao finalizar: gera lote com código, data de fabricação e validade; baixa os insumos crus; registra rendimento real x esperado
- Etiqueta do saco a vácuo impressa na hora: produto, fabricação, validade, lote, peso, conservação (ex.: "manter a -18 °C"), empresa e CNPJ; QR com o código do lote
- Estoque de produto acabado por lote; saída sempre pelo lote que vence primeiro
- Transferência para o bar: lista de separação, leitura do QR da etiqueta, confirmação de recebimento no bar
- Lotes vencendo em 3 dias em amarelo; vencidos bloqueados automaticamente
- Registro diário de temperatura de freezers e câmaras (planilha de controle da Vigilância)
- Rastreio do lote: de quais insumos veio e para quem foi (bar e clientes B2B)

**Critérios de aceite:**

- [ ] Finalizar uma ordem imprime a etiqueta em até 3 segundos
- [ ] Tentar transferir um lote vencido é bloqueado
- [ ] Busca por um código de lote mostra todos os clientes que o receberam
- [ ] Cozinheiro conclui uma ordem de produção sem tocar em teclado, exceto o peso

### Etapa 7. Venda a outros bares e assessoria

**Objetivo:** vender tira-gosto por quilo a outros bares e cobrar a assessoria, com rastreio de lote.

**No Odoo (nativo):** clientes, listas de preço por cliente, pedidos de venda, entrega com lote, faturas e contas a receber. **Programar (`boteco_b2b`):** pedido recorrente com um toque, romaneio com assinatura, contratos da assessoria com mensalidade automática, alerta de cliente parado.

**Entregas:**

- Cadastro de clientes B2B com dados fiscais completos (CNPJ, IE, endereço) para a nota posterior
- Tabela de preço por cliente (padrão R$ 42/kg do plano, editável)
- Pedido B2B: produtos, kg, data de entrega; separação lendo o QR das etiquetas (registra os lotes enviados)
- Romaneio de entrega impresso com assinatura de recebimento
- Contas a receber geradas pelo prazo do cliente; marcação de pago
- Pedido recorrente (ex.: toda quinta, 20 kg de bolinho) com um toque para repetir
- Assessoria: contrato por bar com implantação (R$ 3.500) e mensalidade (R$ 450), gerando as cobranças todo mês
- Histórico de compras por cliente e alerta de cliente que parou de comprar

**Critérios de aceite:**

- [ ] Pedido B2B separado registra os lotes enviados e aparece no rastreio do lote
- [ ] Contrato de assessoria gera a mensalidade do mês seguinte automaticamente
- [ ] Todo pedido B2B entregue entra como pendente no controle fiscal (etapa 9)

### Etapa 8. Financeiro, relatórios e painel do dono

**Objetivo:** o dono abre uma tela e sabe como foi a noite, o mês e cada frente do negócio.

**No Odoo (nativo):** contas a pagar e receber, conciliação bancária, relatórios do PDV e de vendas, exportação para Excel. **Programar (`boteco_painel`):** painel do dono numa tela só, DRE por frente, indicadores do plano contra a meta, relatório de fechamento do dia.

**Entregas:**

- Contas a pagar (fornecedores, aluguel, folha, energia) e a receber (B2B, assessoria), com vencimentos e aviso de atrasados
- Conciliação simples: o caixa do dia vira lançamento por forma de pagamento, com a taxa de cartão configurada
- Fluxo de caixa previsto x realizado
- DRE simples por frente: bar, tira-gosto B2B, assessoria (as três frentes do plano)
- Painel do dono: faturamento da noite, clientes por noite, ticket médio, CMV, itens mais vendidos, tempo médio de entrega, cancelamentos e cortesias, comparação com a mesma noite da semana anterior
- Indicadores do plano lado a lado com a meta: clientes por noite (ponto de equilíbrio de 86), kg vendidos a outros bares, bares com assessoria
- Relatório de fechamento do dia (tipo "redução Z"): vendas, formas de pagamento, cancelamentos, descontos, cortesias, diferença de caixa
- Exportar qualquer relatório para Excel e PDF
- Painel acessível pelo celular do dono fora do bar (via VPN ou túnel seguro)

**Critérios de aceite:**

- [ ] Painel mostra os números da noite em tempo real, atualizando sozinho
- [ ] DRE do mês separa o lucro das três frentes
- [ ] Relatório do dia bate com a soma dos fechamentos de caixa

### Etapa 9. Controle fiscal para emissão posterior

**Objetivo:** o sistema não emite nota, mas garante que toda venda possa ser emitida depois, em outro sistema, sem redigitar nada.

**No Odoo (nativo):** nada emite nota aqui; os dados vêm dos pedidos do PDV e de venda. **Programar (`boteco_fiscal_export`):** tudo desta etapa.

**Entregas:**

- Toda conta fechada no bar gera um registro fiscal "pendente" do tipo NFC-e; todo pedido B2B entregue gera um "pendente" do tipo NF-e
- Cortesia, consumo interno e perda geram "não emitir", com motivo
- Tela "Fiscal" com filtros por período, tipo e status; totais pendentes por dia
- Exportação por período em CSV, Excel e JSON com: dados do emitente, data e hora da venda, itens (código, descrição, NCM, CFOP, CST/CSOSN, unidade, quantidade, valor unitário, desconto), taxa de serviço, formas de pagamento, CPF ou CNPJ do cliente quando houver
- Layout de exportação configurável (ordem e nome das colunas) para casar com o sistema emissor escolhido
- Cada exportação vira um lote numerado; os registros passam para "exportado" e não saem duas vezes, salvo reexportação explícita
- Importação do retorno: planilha com número e chave das notas emitidas marca cada registro como "emitido"
- Relatório de pendências: vendas sem nota há mais de X dias (configurável), com alerta no painel do dono
- Bloqueio de exportação se algum item não tem NCM ou CFOP, com lista do que corrigir

**Critérios de aceite:**

- [ ] Exportar uma noite e importar o retorno deixa zero pendências dessa noite
- [ ] O mesmo registro não sai em dois lotes sem ação explícita
- [ ] A soma dos itens exportados bate com o faturamento do dia

### Etapa 10. Implantação, backup e treinamento

**Objetivo:** colocar no ar no bar e na cozinha central com segurança.

**No Odoo (nativo):** gerenciador de bancos (backup e restauração), atualização de módulos. **Programar:** scripts de backup automático e de atualização com volta em caso de falha, modo treinamento (banco separado de teste).

**Entregas:**

- Backup automático do banco a cada hora num segundo disco e uma vez por dia na nuvem (criptografado); restauração testada com um comando
- Atualização do sistema com um comando, com backup antes e volta automática se falhar
- VPN da cozinha central e acesso remoto do dono
- Plano de contingência impresso: o que fazer se cair o servidor, a rede ou a energia (bloco de comanda em papel, lançamento posterior)
- Modo treinamento: dados de mentira, que não entram no caixa nem no estoque
- Guias de uma página por perfil e vídeos curtos de cada tarefa
- Carga inicial: cardápio, insumos, fichas técnicas, mesas, usuários
- Noite de teste com amigos antes da inauguração, com relatório de problemas

**Critérios de aceite:**

- [ ] Restaurar o backup de ontem num PC limpo leva menos de 30 minutos
- [ ] Cada funcionário executa sua tarefa principal no modo treinamento sem ajuda
- [ ] Desligar o servidor no meio da noite de teste e seguir o plano de contingência não perde vendas

## 8. Requisitos não funcionais

| Tema | Requisito |
| --- | --- |
| Desempenho | Pedido do tablet chega à impressora e à tela em até 2 s; telas abrem em até 1 s na rede local; aguenta 30 tablets e celulares ao mesmo tempo num mini PC com 16 GB de RAM |
| Sem internet | Salão, caixa, produção e estoque funcionam 100% sem internet; só backup na nuvem e acesso remoto dependem dela |
| Queda de aparelho | Tablet e celular guardam o pedido localmente e reenviam; telas reconectam sozinhas ao servidor |
| Queda do servidor | Nobreak de pelo menos 30 min; reinício automático dos serviços; plano em papel (etapa 10) |
| Segurança | PIN com hash; bloqueio após 5 tentativas; rede de clientes separada da rede do sistema; HTTPS na rede interna; acesso externo só por VPN |
| LGPD | Telefone, CPF e dados de clientes só com finalidade clara; tela para apagar ou anonimizar dados a pedido; aviso de privacidade no QR |
| Auditoria | Todo cancelamento, desconto, cortesia, ajuste de estoque, sangria e alteração de preço fica registrado sem possibilidade de apagar |
| Backup | A cada hora local e diário na nuvem; retenção de 30 dias; teste de restauração mensal |
| Compatibilidade | Tablets Android 10+ e iPad (Chrome e Safari); celulares dos últimos 5 anos; impressoras ESC/POS 80 mm por rede |
| Acessibilidade | Contraste mínimo AA; textos de pelo menos 16 px no tablet; funciona com zoom do navegador |
| Manutenção | Código com testes automáticos; cada etapa documentada em `docs/`; logs legíveis guardados por 30 dias |

## 9. Melhorias futuras

Ficam fora desta versão de propósito, para o bar abrir mais cedo. A base (empresa e unidade em toda tabela, registro fiscal, auditoria) já deixa espaço para elas.

| Melhoria | O que traz | Prioridade sugerida |
| --- | --- | --- |
| Versão para vários bares (SaaS da assessoria) | Instalar e cobrar o sistema nos bares atendidos, com painel central da assessoria | Alta |
| PIX com QR dinâmico na mesa | Cliente paga sozinho pelo tablet ou celular e a conta fecha sem o caixa | Alta |
| Integração com maquininha (TEF) | Valor vai direto para a máquina, sem digitar; reduz erro e fraude | Alta |
| Portal de pedidos B2B pelo celular ou WhatsApp | Bares clientes pedem sozinhos, com histórico e catálogo | Alta |
| Previsão de demanda para a cozinha central | Sugere produção pelo histórico, dia da semana, clima e eventos; reduz perda | Média |
| Emissão fiscal integrada | Se um dia valer a pena, troca a exportação por envio direto a uma API de nota | Média |
| Fidelidade e cashback pelo telefone | Traz o cliente de volta e alimenta as ofertas relâmpago | Média |
| Cardápio em TV e telas de ofertas | Divulga happy hour e relâmpago no salão | Média |
| Avaliação rápida no tablet ao fechar a conta | Nota de 1 a 5 e comentário; alerta de nota baixa ao gerente | Média |
| Controle de chope por fluxômetro | Compara litros servidos com vendidos; perda em chope é comum | Média |
| Balança integrada na cozinha central | Peso entra sozinho na ordem de produção e na etiqueta | Média |
| Escala, ponto e gorjeta da equipe | Distribui a taxa de serviço e controla horas | Baixa |
| Delivery e iFood | Vende tira-gosto para o consumidor final em casa | Baixa |
| Reservas de mesa | Útil em dias de show | Baixa |
| Assistente de IA para o dono | Perguntas em português sobre vendas e estoque ("o que mais vendeu sexta?") | Baixa |

## 10. Riscos e decisões pendentes

- [ ] **Momento da nota fiscal (contador):** no varejo, a NFC-e normalmente precisa ser emitida no momento da venda. Confirmar com o contador se a emissão posterior em outro sistema atende o regime de vocês, e em que prazo. O PRD já guarda tudo para qualquer uma das respostas.
- [ ] **Sistema emissor escolhido:** definir qual sistema vai emitir as notas, para fixar o layout de exportação da etapa 9.
- [ ] **Um ou dois CNPJs:** bar e cozinha central na mesma empresa ou separadas (pendência do plano). O sistema aceita os dois.
- [ ] **Sistema do sócio:** decidir se ele é substituído, integrado ou usado como base. Se tiver regras de controle já testadas, elas entram no plano da etapa correspondente.
- [ ] **Propriedade do código:** definir entre os sócios quem é dono do sistema antes de vendê-lo na assessoria.
- [ ] **Registro sanitário da cozinha central:** a etiqueta da etapa 6 precisa trazer o número de registro quando ele sair.
- [ ] **Hardware:** mini PC (16 GB de RAM, SSD 512 GB, por causa do Odoo), nobreak, roteador Wi-Fi dedicado, 2 impressoras térmicas 80 mm de rede, 1 impressora de etiquetas, tablets da mesa com suporte antifurto.

* **Risco de prazo:** 11 etapas feitas por agente de IA ainda precisam de revisão humana a cada etapa. Recomendo abrir o bar com as etapas 0 a 4 e seguir com o resto em produção.

- **Risco de licença (URY):** o URY é AGPL-3. Se algum trecho de código dele for copiado para os módulos `boteco_`, o código de vocês teria de ser aberto ao vender a assessoria. Por isso ele é só modelo de telas e fluxos.
- **Risco de versão do Odoo:** cada versão nova do Odoo (uma por ano) pode quebrar os módulos próprios. Ficar numa versão por pelo menos 2 anos e testar a migração antes de atualizar.
- **Risco de impressora:** se as impressoras escolhidas não forem Epson ePOS, a impressão de pedidos precisa do serviço próprio da Etapa 0. Testar com a impressora real antes de comprar as demais.
- **Risco da localização fiscal:** o l10n\_br nativo do Odoo é básico. Se faltar algum dado para a exportação da Etapa 9 (por exemplo regra de CFOP ou CST por operação), instalar partes da OCA/l10n-brazil 18.0 (l10n\_br\_fiscal) em vez de criar do zero. Como o sistema não emite nota, o mais provável é que o nativo baste.
- **Risco de suporte da 18.0:** a Odoo dá suporte às três últimas versões, então a 18.0 deixa de ter correções quando sair a 21 (previsão: segundo semestre de 2027). Planejar a migração para a 20.0 quando a OCA/l10n-brazil 20.0 estiver estável.

## 11. Como começar no Antigravity

1. Criar uma pasta vazia do projeto e salvar este PRD como `docs/PRD.md`.
2. No Antigravity, abrir a pasta, escolher o modelo Claude e enviar a primeira mensagem abaixo.
3. Revisar o plano que o agente devolver, aprovar, e repetir a cada etapa trocando o número.

```markdown
Leia docs/PRD.md inteiro. A base do sistema é o Odoo Community 18 (github.com/odoo/odoo), rodando em Docker com a imagem oficial. Nunca altere o código do Odoo: tudo o que for novo vai em módulos próprios com prefixo boteco_ na pasta addons/. Use o URY (github.com/ury-erp/ury) só como referência de telas e fluxos de restaurante; não copie código dele, porque a licença é AGPL. Antes de programar algo do zero, veja se a OCA (github.com/OCA/pos e github.com/OCA/l10n-brazil, branch 18.0) já resolve: módulo LGPL pode ser instalado, módulo AGPL serve só de estudo. Siga a seção 5 (arquitetura e regras) e a seção 4 (facilidade de uso). Comece pela Etapa 0. Antes de escrever código, me mostre o plano da etapa: o que é configuração nativa do Odoo, o que vira módulo próprio, as telas, os testes e como vou verificar cada critério de aceite. Não avance para a próxima etapa sem minha aprovação.
```
