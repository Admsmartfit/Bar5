# Manual de Testes e Desenvolvimento no Windows 11
> **Sistema Boteco Raiz (Odoo 18 + PostgreSQL)**  
> *Guia passo a passo para iniciantes e leigos rodarem e testarem o sistema no Windows 11.*

---

## 📋 Índice
1. [Visão Geral](#1-visão-geral)
2. [Pré-requisitos no Windows 11](#2-pré-requisitos-no-windows-11)
3. [Passo a Passo de Instalação e Execução](#3-passo-a-passo-de-instalação-e-execução)
4. [Como Carregar Dados de Exemplo (Cardápio e Equipe)](#4-como-carregar-dados-de-exemplo-cardápio-e-equipe)
5. [Como Acessar o Sistema no Navegador](#5-como-acessar-o-sistema-no-navegador)
6. [Como Executar os Testes Automáticos](#6-como-executar-os-testes-automáticos)
7. [Comandos Úteis do Dia a Dia](#7-comandos-úteis-do-dia-a-dia)
8. [Resolução de Problemas Comuns](#8-resolução-de-problemas-comuns)

---

## 1. Visão Geral
Este manual ensina como preparar seu computador com **Windows 11** para rodar o **Sistema Boteco Raiz** em ambiente de teste local. 

Mesmo que o servidor final seja um computador rodando Linux (Debian/Ubuntu), você pode simular e testar todas as funcionalidades (PDV, Cozinha/KDS, Cardápio, Estoque, Painel do Dono) diretamente no seu Windows 11 utilizando **Docker Desktop**.

---

## 2. Pré-requisitos no Windows 11

Antes de começar, você precisa ter 2 programas instalados no Windows 11:

### 2.1. Docker Desktop para Windows
O Docker é a ferramenta que "conteineriza" o banco de dados PostgreSQL e o servidor Odoo.
1. Baixe o instalador oficial no site: [Docker Desktop for Windows](https://www.docker.com/products/docker-desktop/)
2. Durante a instalação, mantenha marcada a opção **"Use WSL 2 instead of Hyper-V"** (recomendado).
3. Após instalar, reinicie o computador se o instalador solicitar.
4. **IMPORTANTE:** Abra o aplicativo **Docker Desktop** no Windows e verifique se no canto inferior esquerdo a luzinha está verde ou se o ícone da baleia no canto da barra de tarefas está ativo.

### 2.2. Git para Windows (Git Bash)
O Git Bash é um terminal no Windows que aceita os mesmos comandos de terminal Linux (`.sh`).
1. Baixe o instalador oficial: [Git for Windows](https://git-scm.com/download/win)
2. Instale mantendo as opções padrão (basta avançar clicando em *Next*).

---

## 3. Passo a Passo de Instalação e Execução

Siga os passos abaixo na ordem indicada:

### Passo 1: Abrir o Terminal na pasta do projeto
1. Abra o **Explorador de Arquivos** do Windows 11 e navegue até a pasta do projeto (`c:\Users\ralan\programa\Bar5`).
2. Clique com o **botão direito do mouse** num espaço em branco da pasta e selecione **"Open Git Bash here"** (ou "Abrir Git Bash aqui").
3. Uma janela preta/escura de terminal será aberta.

### Passo 2: Executar o script de instalação para desenvolvimento
No terminal Git Bash, digite o seguinte comando e pressione **ENTER**:

```bash
./instalar.sh --dev
```

> 💡 **O que este comando faz automaticamente?**
> - Cria o arquivo `.env` com senhas aleatórias e seguras.
> - Gera os certificados de conexão de teste (`config/certs/`).
> - Baixa e inicia o banco de dados PostgreSQL 16.
> - Prepara e instala os 10 módulos nativos do Odoo e os módulos `boteco_*`.
> - Cria a estrutura inicial com moeda em Real (R$) e fuso horário do Brasil.

O processo pode levar entre 3 a 7 minutos na primeira vez. Ao finalizar, o terminal exibirá a mensagem de sucesso: `Pronto em X min Y s`.

---

## 4. Como Carregar Dados de Exemplo (Cardápio e Equipe)

Para testar o sistema sem precisar cadastrar tudo do zero, você pode inserir os dados de demonstração (produtos, mesas, usuários e PINs de equipe):

No terminal Git Bash, execute:

```bash
docker compose run --rm -T odoo odoo shell -c /etc/odoo/odoo.conf -d boteco --no-http < scripts/dados_exemplo.py
```

---

## 5. Como Acessar o Sistema no Navegador

Após a instalação terminar, abra o seu navegador (Google Chrome, Microsoft Edge ou Firefox).

### 5.1. Endereços de Acesso
- **Painel de Login (Dono / Administrador):**  
  `https://localhost/web/login`  
  ou  
  `https://127.0.0.1/web/login`
- **Tela de Login por PIN (Atendentes e Garçons):**  
  `https://localhost/boteco/pin`
- **Status de Saúde do Sistema:**  
  `https://localhost/boteco/saude`

### 5.2. Como Passar pelo Aviso de Segurança do Navegador
Como o sistema gera um certificado local para testes, o navegador exibirá o aviso: *"Sua conexão não é privada"* ou *"Sua conexão não é segura"*.

**Como prosseguir:**
1. No **Google Chrome / Microsoft Edge**: Clique no botão **"Avançado"** (ou *Advanced*) e depois clique no link **"Ir para localhost (não seguro)"**.
2. No **Firefox**: Clique em **"Avançado"** e depois em **"Aceitar o risco e continuar"**.

### 5.3. Dados de Login
- **Usuário Administrador (Dono):** `admin`
- **Senha Administrador:** Abra o arquivo `.env` localizado na pasta do projeto e procure a linha `ODOO_ADMIN_USER_PASSWORD=...`. A senha estará após o sinal de igual `=`.
- **PIN de teste da equipe:** Padrões cadastrados no script de exemplo (ex: Garçom `1234`, Gerente `9999`).

---

## 6. Como Executar os Testes Automáticos

Para garantir que todos os 104 testes dos módulos estão passando corretamente no seu ambiente Windows 11:

No terminal Git Bash, execute:

```bash
./scripts/testar.sh
```

Se desejar testar apenas um módulo específico (por exemplo, `boteco_base`):

```bash
./scripts/testar.sh boteco_base
```

---

## 7. Comandos Úteis do Dia a Dia

Aqui estão os principais comandos que você precisará usar no terminal Git Bash:

| O que você quer fazer | Comando a digitar no Git Bash |
| :--- | :--- |
| **Ver logs em tempo real** | `docker compose logs -f odoo` |
| **Parar o sistema** | `docker compose stop` |
| **Religar o sistema** | `docker compose start` |
| **Reiniciar do zero** | `docker compose down` e depois `./instalar.sh --dev` |
| **Ativar Modo Treinamento** | `./scripts/treinamento.sh` (Acessível em `https://localhost:8443`) |
| **Fazer Backup Imediato** | `docker compose exec backup bash /usr/local/bin/backup-loop.sh --uma-vez` |

---

## 8. Resolução de Problemas Comuns

### ❓ Erro: "Docker não encontrado" ou "O Docker não está rodando"
- **Solução:** Abra o aplicativo **Docker Desktop** no menu Iniciar do Windows e aguarde até que o ícone da baleia pare de piscar na barra de tarefas.

### ❓ Erro: "Porta 80 ou 443 já está em uso"
- **Causa:** Outro programa do Windows (como IIS, Skype ou VMware) pode estar usando a porta de internet.
- **Solução:** Feche programas que ocupam essas portas ou abra o CMD como Administrador e execute `net stop w3svc` para parar o IIS do Windows.

### ❓ Esqueci a senha do Administrador
- **Solução:** Abra o arquivo `.env` na pasta do projeto usando o Bloco de Notas ou VS Code e veja o valor definido na linha `ODOO_ADMIN_USER_PASSWORD`.
