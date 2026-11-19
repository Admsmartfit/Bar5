# Integração de cotações (serviço externo → Odoo)

*Desde 19/11/2026, o Odoo não conversa com WhatsApp, sites, Instagram nem fotos.* Isso fica num **serviço externo**, por exemplo n8n + Evolution API + IA. O serviço lê as mensagens e catálogos dos fornecedores, identifica produto, unidade e preço, e manda **só dados limpos** para o Odoo. O Odoo é o cérebro financeiro e de estoque:
- grava a cotação;
- atualiza o preço do fornecedor e o pedido de cotação em aberto;
- gera as oportunidades de compra e as ideias de promoção.

```
WhatsApp / sites / Instagram / fotos ──► [n8n + Evolution API + IA] ──HTTPS + token──► Odoo (API de cotações)
                                            (fora do servidor do PDV)                   radar · alertas · lista de compras
```

## Endereço e token
Os dois ficam em **Compras e estoque › Comprar › Integração de cotações**. Só o dono vê o token e pode trocá-lo.

```
POST https://<servidor>/api/boteco/webhook/cotacao_recebida
Authorization: Bearer <token>        (ou:  X-API-Key: <token>)
Content-Type: application/json
```

Regras de acesso:
* Vindo de fora da rede do servidor, a chamada precisa ser HTTPS. Na mesma rede, por exemplo o n8n no mesmo servidor chamando `http://odoo:8069`, HTTP é aceito.
* O limite é de 120 chamadas por minuto.
* Toda chamada fica registrada em *Configuração › Acompanhamento › Registro da API de cotações*.

## Corpo (um item ou vários)
```json
{
  "id_fornecedor": "atacadao",
  "id_produto_interno": "CERV-600",
  "codigo_barras": "7891149101010",
  "unidade_medida": "cx",
  "quantidade_embalagem": 24,
  "preco_cotado": 189.90,
  "descricao": "Brahma 600ml cx c/24",
  "referencia": "whatsapp:msg-123",
  "condicao_promocional": "leve 4 pague 3",
  "link_comprovante": "https://.../encarte.jpg"
}
```
Só com o nome (o n8n não sabe o código do Odoo) e o telefone de quem mandou:
```json
{"telefone_origem": "5528999991234", "produto_nome_bruto": "Alcatra Grill",
 "unidade_medida": "kg", "preco_cotado": 49.90}
```
Vários itens de uma vez: `{"cotacoes": [ {...}, {...} ]}` (até 500).

| Campo | Obrigatório | O que é |
|---|---|---|
| `id_fornecedor` | um dos dois | O **ID no serviço de cotações** do cadastro do fornecedor, ou o número do fornecedor no Odoo |
| `telefone_origem` | um dos dois | Telefone de quem mandou a mensagem. O Odoo procura no telefone/celular dos fornecedores e dos contatos deles (DDD + 8 últimos dígitos, com ou sem o 9 e o 55). Se o número estiver em mais de um fornecedor, recusa |
| `id_produto_interno` | não | O **código interno** do insumo (`default_code`), ou o número do produto no Odoo |
| `codigo_barras` | não | EAN do insumo; tem prioridade sobre o código interno |
| `produto_nome_bruto` | não | O nome como o fornecedor escreveu (ex.: "Alcatra Grill"). Usado quando não vem código nem EAN |
| `unidade_medida` | sim | `un`, `kg`, `g`, `l`, `ml`, `dz`; ou embalagem: `cx`, `fardo`, `pct`, `saco`, `bandeja`, `pack` |
| `quantidade_embalagem` | se for embalagem | Unidades do insumo na embalagem (ex.: 24 latas na caixa) |
| `preco_cotado` | sim | Preço em reais da unidade informada (ponto ou vírgula decimal) |
| `condicao_promocional` | não | A condição da oferta (ex.: "leve 4 pague 3", "acima de 10 cx"). Aparece ao lado do preço no Radar e na revisão |
| `link_comprovante` | não | Endereço `https://` da foto ou do encarte original. Vira o botão "Ver encarte" no Radar e na revisão (outros tipos de link são ignorados) |
| `descricao`, `referencia` | não | Como veio escrito e de onde veio |

O fornecedor encontrado precisa estar com *Aceitar cotações automáticas* marcado; se estiver desmarcado, o item volta com `status: "recusado"`.

**Como o produto é identificado:** código de barras → código interno → **sinônimos** (*Compras › Sinônimos de produtos*) → de-para da NF-e e nome no cadastro do fornecedor. Se nada bater, o item **não é rejeitado**: entra em *Cotações para revisar* com `status: "revisar"`, já com a sugestão de insumo mais parecida marcada. Quando o gerente toca em **Ligar**, o nome vira sinônimo daquele fornecedor, e da próxima vez o preço entra sozinho. Nome só "parecido" nunca grava preço sozinho.

O Odoo converte para a unidade do insumo. Por exemplo: R$ 189,90 a caixa com 24 vira R$ 7,91 a garrafa, e R$ 0,0036 o grama vira R$ 3,60 o kg. Se a unidade não converter (kg para um insumo em unidade, ou caixa sem quantidade), o item vai para *Cotações para revisar*.

## Resposta
```json
{"ok": true, "aplicados": 1, "resultados": [
  {"indice": 0, "status": "ok", "produto_id": 42, "preco_unidade_insumo": 7.9125, "rfq_atualizadas": 1, "oportunidade_id": 7}
]}
```

Valores de `status`:

| `status` | O que significa |
|---|---|
| `ok` | Aplicado |
| `revisar` | Produto ou unidade não reconhecidos; foi para *Cotações para revisar*, e `motivo` diz por quê |
| `recusado` | Fornecedor desconhecido ou preço inválido |
| `erro` | Erro inesperado naquele item |

Códigos HTTP de erro:

| Código | Quando |
|---|---|
| `401` | Token errado ou ausente |
| `400` | JSON inválido |
| `429` | Acima do limite por minuto |
| `503` | Recebimento desligado na Central de Recursos |

## O que o Odoo faz com cada preço aplicado
1. **Radar de preços**: guarda no histórico com a origem "Serviço de cotações (API)".
2. **Preço do fornecedor** no cadastro do insumo.
3. **Pedido de cotação em aberto** (rascunho ou enviado) desse fornecedor com o insumo: o preço da linha é atualizado em silêncio.
4. **Oportunidade de compra**: se o preço estiver X% abaixo (padrão 10%) do **preço médio ponderado das últimas 3 compras confirmadas** (sem compras, vale o custo médio atual):
   * aviso no Painel do dono e pendência para os gerentes;
   * **sugestão de compra maior**: estoque para N dias de consumo (padrão 21) ou até o estoque máximo, o que for maior. Entra sozinha na *Lista de compras*;
   * **ideia de promoção**: para cada item do cardápio que leva o insumo (receita) ou que é o próprio insumo (revenda), o sistema calcula o custo novo e o preço de uma **Oferta relâmpago** que mantém a margem % de hoje. O gerente cria a oferta com 1 toque e lança no PDV e no autoatendimento.

Os ajustes ficam em *Configuração › Liga / desliga recursos › Compras inteligentes*: % de queda, dias de estoque e "só insumos chave". O "insumo chave" é marcado no cadastro do produto.

## O que saiu do Odoo nesta mudança
* Conexão do WhatsApp por QR Code, sessão e verificação de conexão (Evolution API dentro do compose).
* Coletor de sites e Instagram, a biblioteca `instaloader` e as tarefas agendadas do Instagram.
* Leitura de foto de encarte por IA. Continua no Odoo a leitura manual de **PDF ou texto colado**, que não acessa a internet.
* Campos de raspagem no fornecedor (Instagram, site de ofertas, palavras-chave). No lugar, fica o **ID no serviço de cotações**.
