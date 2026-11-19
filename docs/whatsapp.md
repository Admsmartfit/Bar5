# WhatsApp do bar e coletor de ofertas (Etapa 35)

Duas peças opcionais, cada uma no seu contêiner. Elas não pesam no caixa e não ficam expostas na internet.

| Peça | O que faz | Como ligar no servidor |
| :--- | :--- | :--- |
| **Evolution API** (`evolution`) | Conecta o WhatsApp do bar por QR Code, como o WhatsApp Web, e avisa o Odoo a cada mensagem | `./scripts/ligar_cotacoes.sh whatsapp` |
| **Coletor** (`coletor`) | Lê o site e o Instagram dos fornecedores (Instagram 1x por dia; sites 2x por semana) | `./scripts/ligar_cotacoes.sh coletor` |

## WhatsApp
1. No servidor, rode `./scripts/ligar_cotacoes.sh whatsapp`. O script:
   * cria a chave `EVOLUTION_API_KEY` no `.env`;
   * cria o banco `evolution`;
   * sobe o contêiner;
   * passa a chave para o Odoo.
2. No Odoo, entre como **dono** e abra **Configuração › Sistema › WhatsApp (conectar)**. Toque em **Conectar WhatsApp**.
3. No **celular do bar**, abra o WhatsApp › ⋮ › **Dispositivos conectados** › **Conectar um dispositivo** e leia o QR Code.
4. Cadastre o **celular de cada fornecedor** no cadastro dele. A opção *Aceitar cotações automáticas* vem marcada.

O que acontece depois:
* **Mensagem de fornecedor cadastrado:** entra na fila. O preço vai para o *Radar de preços* com origem "WhatsApp do fornecedor" e para o preço do fornecedor no produto. O que o sistema não reconhece vai para *Compras › Cotações para revisar*.
* **Mensagem de qualquer outro número (clientes, grupos, família):** é descartada na hora, sem gravar. Se tinha preço, o Painel do dono só avisa que "1 número não cadastrado mandou preços".
* **Conexão caiu:** aparece um aviso no Painel do dono e na página *Saúde do sistema* (a conexão é conferida a cada 5 minutos). Leia o QR de novo.
* **Privacidade (LGPD):** o texto e os arquivos da mensagem são apagados assim que lidos (a fila é limpa em 30 dias). O registro das chamadas fica em *Configuração › Acompanhamento › Registro do WhatsApp e coletor*.

**Riscos:**
* A conexão não é oficial. O WhatsApp pode derrubar a sessão ou, em casos raros, bloquear o número. Por isso use o número do bar, não o pessoal.
* Celular muitos dias sem internet também derruba a sessão.

## Coletor
1. No cadastro do fornecedor, preencha **Instagram**, **Site / encarte de ofertas** e, se quiser, as **palavras-chave**.
2. No servidor, rode `./scripts/ligar_cotacoes.sh coletor`. Ele pega o token no Odoo, grava em `BOTECO_COLETOR_TOKEN` no `.env` e sobe o contêiner.
3. Os horários ficam em **Compras › WhatsApp e coletor**. O padrão é: Instagram às 8:00, sites às segundas e quintas às 8:00.

Detalhes:
* Enquanto o coletor dá sinal de vida, o Odoo deixa de ler o Instagram por conta própria: robô fora do servidor do PDV.
* Se o coletor parar por mais de 2 dias, o Odoo volta a ler o Instagram 1x por dia, como antes.
* **Tokens:** cada integração tem o seu. Para trocar, use *Compras › WhatsApp e coletor* (só o dono). Depois de trocar o do coletor, rode o script de novo. Depois de trocar o do WhatsApp, toque em *Conectar WhatsApp* de novo.
