# Manual de Instalação e Produção no Servidor Linux
> **Sistema Boteco Raiz (Odoo 18 + PostgreSQL)**  
> *Guia definitivo para instalação, configuração e manutenção do servidor de produção em Linux (Debian/Ubuntu).*

---

## 📋 Índice
1. [Visão Geral e Requisitos de Hardware](#1-visão-geral-e-requisitos-de-hardware)
2. [Pré-requisitos do Sistema Operacional](#2-pré-requisitos-do-sistema-operacional)
3. [Instalação com Um Único Comando](#3-instalação-com-um-único-comando)
4. [Configuração do Arquivo de Ambiente (.env)](#4-configuração-do-arquivo-de-ambiente-env)
5. [Instalação do Certificado HTTPS nos Tablets/Celulares](#5-instalação-do-certificado-https-nos-tabletscelulares)
6. [Endereços de Acesso da Rede Interna](#6-endereços-de-acesso-da-rede-interna)
7. [Rotinas de Backup Automático e Nuvem](#7-rotinas-de-backup-automático-e-nuvem)
8. [Atualizações Seguras do Sistema](#8-atualizações-seguras-do-sistema)
9. [Restauração em Caso de Emergência](#9-restauração-em-caso-de-emergência)
10. [Diagnóstico e Solução de Problemas](#10-diagnóstico-e-solução-de-problemas)

---

## 1. Visão Geral e Requisitos de Hardware

O servidor de produção do **Sistema Boteco Raiz** foi otimizado para rodar em um **Mini PC** ou servidor com as seguintes especificações mínimas:

- **Processador:** Quad-Core 64-bit (Intel N100, i3/i5 ou equivalente AMD/ARM).
- **Memória RAM:** 8 GB a 16 GB RAM (o script ajusta os parâmetros de memória do PostgreSQL e Odoo automaticamente).
- **Armazenamento:** SSD NVMe ou SATA de 128 GB ou superior.
- **Sistema Operacional:** Linux **Debian 12 (Bookworm)** ou **Ubuntu 22.04 / 24.04 LTS** (instalação limpa/server).
- **Rede:** Conexão via cabo Ethernet (cabo de rede RJ45 conectado ao roteador principal do bar).

---

## 2. Pré-requisitos do Sistema Operacional

Em um servidor Linux limpo recém-formatado, conecte-se via SSH ou abra o terminal diretamente na máquina com usuário `sudo` ou `root`.

Atualize os pacotes do sistema operacional:

```bash
sudo apt update && sudo apt upgrade -y
sudo apt install -y git curl
```

---

## 3. Instalação com Um Único Comando

### Passo 1: Copiar os arquivos do projeto para o servidor
Clone o repositório ou copie a pasta do projeto `Bar5` para o diretório de sua preferência no servidor (exemplo: `/opt/boteco` ou `/home/seu_usuario/bar5`):

```bash
cd /opt/
sudo git clone <URL_DO_REPOSITORIO> boteco
cd /opt/boteco
```

*(Se você apenas transferiu os arquivos compactados via Pendrive/SCP, descompacte e entre na pasta do projeto).*

### Passo 2: Executar o instalador de produção
Execute o script de instalação como superusuário (`sudo`):

```bash
sudo ./instalar.sh
```

> ⚡ **O que o instalador faz sozinho:**
> 1. Instala o **Docker** e o **Docker Compose v2** automaticamente (se ainda não estiverem instalados).
> 2. Instala e ativa o serviço **Avahi Daemon** para permitir o endereço fácil `https://boteco.local` na rede sem precisar fixar IP manual nos tablets.
> 3. Gera o arquivo `.env` com senhas aleatórias e ultra-seguras de 24 caracteres para o banco de dados e para o Odoo.
> 4. Cria o certificado digital HTTPS interno válido por 10 anos.
> 5. Inicializa o banco PostgreSQL 16 em Português do Brasil com fuso de São Paulo e moeda em Real (R$).
> 6. Instala todos os módulos nativos e os módulos customizados do bar (`boteco_*`).
> 7. Configura os armazéns, PDV de restaurante com 20 mesas e telas de cozinha.
> 8. Configura o agendamento no sistema (`systemd`) para backup automático diário na nuvem às 07:30 da manhã.

---

## 4. Configuração do Arquivo de Ambiente (.env)

Após a conclusão da instalação inicial, abra o arquivo de configurações para colocar as informações reais da sua empresa:

```bash
sudo nano .env
```

Ajuste os seguintes campos principais:

```env
# Dados da Empresa (Bar principal)
EMPRESA_NOME="Seu Boteco Raiz Ltda"
EMPRESA_CNPJ="00.000.000/0001-00"
EMPRESA_CIDADE="São Paulo"

# Nome na rede local (padrão: boteco.local)
BOTECO_HOSTNAME=boteco.local

# Faixa de IP da rede para os tablets e garçons
REDE_CLIENTES=192.168.1.0/24

# Backup na Nuvem (Rclone / Google Drive / S3)
BACKUP_NUVEM_REMOTE=gdrive_boteco:backups
```

Para salvar e sair do editor Nano: Pressione `Ctrl + O`, depois `ENTER`, e por fim `Ctrl + X`.

Depois de alterar o `.env`, aplique as alterações reiniciando o serviço:

```bash
docker compose up -d
```

---

## 5. Instalação do Certificado HTTPS nos Tablets/Celulares

Para que os tablets, telefones dos garçons e impressoras de cozinha acessem `https://boteco.local` sem alertas de aviso de segurança:

1. O instalador gera o arquivo de certificado na pasta: `config/certs/boteco.crt`.
2. Transfira o arquivo `boteco.crt` para os tablets (via Pendrive, WhatsApp ou servidor web local).
3. No Android / iPadOS: Acesse **Configurações > Segurança > Instalar Certificado do Usuário / CA** e selecione o arquivo `boteco.crt`.

---

## 6. Endereços de Acesso da Rede Interna

Após a instalação, qualquer dispositivo conectado ao Wi-Fi/Rede do bar poderá acessar:

| Serviço / Perfil | Endereço URL | Finalidade |
| :--- | :--- | :--- |
| **Entrada com PIN (Equipe)** | `https://boteco.local/boteco/pin` | Tela rápida para garçons e atendentes |
| **Painel de Gestão (Dono)** | `https://boteco.local/web/login` | Acesso completo com login/senha do admin |
| **Status de Saúde / Monitor** | `https://boteco.local/boteco/saude` | Ver se banco, Odoo e impressoras estão OK |
| **Modo Treinamento** | `https://boteco.local:8443` | Teste sem afetar o banco oficial da loja |

---

## 7. Rotinas de Backup Automático e Nuvem

O sistema possui **dupla camada de backup**:

1. **Backup Local Automático (A cada 60 minutos):**
   - É gerado pelo contêiner `backup` e fica salvo na pasta `./backups`.
   - Mantém o histórico dos últimos 30 dias por padrão.

2. **Backup na Nuvem (Diário às 07:30h):**
   - O agendador do Linux (`boteco-backup-nuvem.timer`) roda todos os dias após o fechamento da casa.
   - Para disparar um backup manual imediatamente, execute:
     ```bash
     docker compose exec backup bash /usr/local/bin/backup-loop.sh --uma-vez
     ```

---

## 8. Atualizações Seguras do Sistema

Quando o desenvolvedor disponibilizar novidades ou correções no código, você pode atualizar o servidor de produção com total segurança.

Execute o script de atualização:

```bash
sudo ./scripts/atualizar.sh --git
```

> 🛡️ **Mecanismo de Segurança:**
> O script de atualização faz um backup completo antes de alterar qualquer código. Se a atualização encontrar qualquer erro nos testes ou na inicialização dos módulos, ele faz **rollback automático** e restaura a versão anterior que estava funcionando.

---

## 9. Restauração em Caso de Emergência

Se precisar restaurar um backup antigo (por substituição de servidor ou teste):

1. Liste os arquivos de backup disponíveis na pasta `./backups`:
   ```bash
   ls -la backups/
   ```
2. Restaure o backup mais recente:
   ```bash
   sudo ./scripts/restaurar.sh
   ```
   *Ou informe um arquivo específico:*
   ```bash
   sudo ./scripts/restaurar.sh backups/boteco_20261007_120000.dump
   ```

---

## 10. Diagnóstico e Solução de Problemas

### 🔍 Ver logs em tempo real do sistema
```bash
docker compose logs -f odoo
```

### 🔄 Reiniciar todos os serviços
```bash
docker compose restart
```

### 🩺 Verificar se os contêineres estão saudáveis
```bash
docker compose ps
```

Todos os serviços (`db`, `odoo`, `nginx`, `backup`) devem estar com a situação **`Up (healthy)`** ou **`running`**.
