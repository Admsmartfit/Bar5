#!/usr/bin/env bash
# =============================================================================
#  Sistema Boteco Raiz — instalação com um comando
#
#  Num mini PC Linux limpo (Debian/Ubuntu):   sudo ./instalar.sh
#  Em máquina de desenvolvimento:            ./instalar.sh --dev
#
#  O que faz (pode rodar de novo sem medo: cada passo verifica se já foi feito):
#    1. Instala Docker e Avahi (nome boteco.local) se faltarem       [só Linux]
#    2. Cria o .env com senhas aleatórias                              [se não existir]
#    3. Gera config/odoo.conf e o certificado HTTPS da rede interna
#    4. Sobe o PostgreSQL, cria o banco em pt_BR, fuso de São Paulo, real (R$),
#       instala os módulos nativos + boteco_* e configura empresa/armazéns/PDV
#    5. Sobe Odoo, Nginx e backup automático; agenda o backup na nuvem
# =============================================================================
set -Eeuo pipefail
export MSYS_NO_PATHCONV=1  # Git Bash no Windows: não converter /etc/... em C:/...

cd "$(dirname "$0")"
RAIZ="$(pwd)"

VERDE='\033[1;32m'; AMARELO='\033[1;33m'; VERMELHO='\033[1;31m'; NORMAL='\033[0m'
passo()  { echo -e "\n${VERDE}==> $*${NORMAL}"; }
aviso()  { echo -e "${AMARELO}AVISO: $*${NORMAL}"; }
falha()  { echo -e "${VERMELHO}ERRO: $*${NORMAL}" >&2; exit 1; }
trap 'falha "a instalação parou na linha $LINENO. Veja a mensagem acima e rode ./instalar.sh de novo."' ERR

MODO_DEV=0
for arg in "$@"; do
  case "$arg" in
    --dev) MODO_DEV=1 ;;
    -h|--help) sed -n '2,16p' "$0"; exit 0 ;;
  esac
done

INICIO=$(date +%s)
E_LINUX=0; [[ "$(uname -s)" == "Linux" ]] && E_LINUX=1

# Módulos nativos (seção 5 do PRD) + módulos próprios
MODULOS_NATIVOS="point_of_sale,pos_restaurant,pos_self_order,stock,purchase,mrp,pos_mrp,sale_management,account,l10n_br"
MODULOS_BOTECO="${MODULOS_BOTECO:-boteco_base,boteco_cardapio,boteco_pos,boteco_kds,boteco_autoatendimento,boteco_estoque,boteco_cozinha_central,boteco_b2b,boteco_painel,boteco_fiscal_export}"
MODULOS="${MODULOS:-$MODULOS_NATIVOS,$MODULOS_BOTECO}"

# -----------------------------------------------------------------------------
passo "1/6 Conferindo pré-requisitos"
if [[ $E_LINUX -eq 1 && $MODO_DEV -eq 0 ]]; then
  [[ $EUID -eq 0 ]] || falha "rode com sudo: sudo ./instalar.sh"
  if ! command -v docker >/dev/null 2>&1; then
    echo "Instalando Docker..."
    apt-get update -qq
    apt-get install -y -qq ca-certificates curl openssl gettext-base
    curl -fsSL https://get.docker.com | sh
  fi
  systemctl enable --now docker >/dev/null 2>&1 || true
  if ! command -v avahi-daemon >/dev/null 2>&1; then
    apt-get install -y -qq avahi-daemon libnss-mdns
  fi
  NOME_HOST="$(grep -E '^BOTECO_HOSTNAME=' .env 2>/dev/null | cut -d= -f2 || true)"
  NOME_HOST="${NOME_HOST:-boteco.local}"
  hostnamectl set-hostname "${NOME_HOST%%.local}" || true
  systemctl enable --now avahi-daemon >/dev/null 2>&1 || true
fi
command -v docker >/dev/null 2>&1 || falha "Docker não encontrado. Instale o Docker e rode de novo."
docker compose version >/dev/null 2>&1 || falha "Docker Compose v2 não encontrado (comando 'docker compose')."
docker info >/dev/null 2>&1 || falha "O Docker não está rodando. Inicie o Docker e rode de novo."

gerar_senha() { openssl rand -base64 32 2>/dev/null | tr -dc 'A-Za-z0-9' | head -c 24 || date +%s%N | sha256sum | head -c 24; }

# -----------------------------------------------------------------------------
passo "2/6 Arquivo de configuração .env"
if [[ ! -f .env ]]; then
  cp .env.example .env
  sed -i.bak "s|^POSTGRES_PASSWORD=.*|POSTGRES_PASSWORD=$(gerar_senha)|" .env
  sed -i.bak "s|^ODOO_ADMIN_PASSWD=.*|ODOO_ADMIN_PASSWD=$(gerar_senha)|" .env
  sed -i.bak "s|^ODOO_ADMIN_USER_PASSWORD=.*|ODOO_ADMIN_USER_PASSWORD=$(gerar_senha)|" .env
  if [[ $MODO_DEV -eq 1 ]]; then
    sed -i.bak "s|^BACKUP_DIR=.*|BACKUP_DIR=./backups|" .env
  fi
  rm -f .env.bak
  chmod 600 .env
  echo "Criado .env com senhas aleatórias. Guarde uma cópia em local seguro."
else
  echo ".env já existe, mantendo."
fi
set -a; # shellcheck disable=SC1091
source .env; set +a
: "${BOTECO_DB:=boteco}" "${ODOO_WORKERS:=4}" "${ODOO_MAX_CRON_THREADS:=1}" "${BACKUP_DIR:=./backups}"
export BOTECO_DB ODOO_WORKERS ODOO_MAX_CRON_THREADS
mkdir -p "$BACKUP_DIR"
# Pasta da tela "Atualizar sistema": o Odoo (usuário do contêiner) grava o pedido, o agente do servidor lê
mkdir -p atualizacao && chmod 777 atualizacao

# -----------------------------------------------------------------------------
passo "3/6 Gerando config/odoo.conf e certificado HTTPS"
renderizar() {
  # envsubst só com as variáveis que usamos, para não estragar outros '$'
  local conteudo; conteudo="$(cat "$1")"
  for var in ODOO_ADMIN_PASSWD POSTGRES_USER POSTGRES_PASSWORD BOTECO_DB ODOO_WORKERS ODOO_MAX_CRON_THREADS; do
    conteudo="${conteudo//\$\{$var\}/${!var}}"
  done
  printf '%s\n' "$conteudo" > "$2"
}
renderizar config/odoo.conf.template config/odoo.conf
chmod 640 config/odoo.conf

mkdir -p config/certs
if [[ ! -f config/certs/boteco.crt ]]; then
  IP_LOCAL="$( (hostname -I 2>/dev/null || echo 127.0.0.1) | awk '{print $1}')"
  openssl req -x509 -nodes -newkey rsa:2048 -days 3650 \
    -keyout config/certs/boteco.key -out config/certs/boteco.crt \
    -subj "/CN=${BOTECO_HOSTNAME:-boteco.local}/O=${EMPRESA_NOME:-Boteco}" \
    -addext "subjectAltName=DNS:${BOTECO_HOSTNAME:-boteco.local},DNS:localhost,IP:127.0.0.1,IP:${IP_LOCAL}" \
    >/dev/null 2>&1
  chmod 600 config/certs/boteco.key
  echo "Certificado criado (vale 10 anos). Instale config/certs/boteco.crt nos tablets para não ver aviso."
fi

# -----------------------------------------------------------------------------
passo "4/6 Banco de dados e módulos"
docker compose pull -q --ignore-buildable
docker compose build --pull -q odoo
docker compose up -d db
for i in $(seq 1 60); do
  docker compose exec -T db pg_isready -U "$POSTGRES_USER" >/dev/null 2>&1 && break
  sleep 2
done

# Instala (-i) ou atualiza (-u) módulos; em caso de erro mostra o trecho do log e para.
instalar_modulos() {
  local log; log="$(mktemp)"
  if ! docker compose run --rm -T odoo odoo -c /etc/odoo/odoo.conf -d "$BOTECO_DB" --workers=0 \
      --without-demo=all "$1" "$2" --stop-after-init --logfile= > "$log" 2>&1; then
    grep -E " (ERROR|CRITICAL) " -A25 "$log" | tail -60
    falha "a instalação dos módulos falhou (log completo: $log)"
  fi
  if grep -qE " (ERROR|CRITICAL) " "$log"; then
    aviso "a instalação registrou erros; confira $log"
  fi
}

BANCO_EXISTE="$(docker compose exec -T db psql -U "$POSTGRES_USER" -d postgres -tAc \
  "SELECT 1 FROM pg_database WHERE datname='${BOTECO_DB}'" | tr -d '[:space:]')"

if [[ "$BANCO_EXISTE" != "1" ]]; then
  echo "Criando o banco '${BOTECO_DB}' em português do Brasil..."
  docker compose run --rm -T odoo odoo -c /etc/odoo/odoo.conf -d "$BOTECO_DB" --workers=0 \
    --load-language=pt_BR --without-demo=all -i base --stop-after-init --logfile= >/dev/null
  # Empresa brasileira ANTES da contabilidade: o Odoo carrega o plano de contas do Brasil
  docker compose run --rm -T odoo odoo shell -c /etc/odoo/odoo.conf -d "$BOTECO_DB" --no-http \
    --workers=0 --logfile= < scripts/pre_configurar.py
  echo "Instalando módulos (leva alguns minutos)..."
  instalar_modulos -i "$MODULOS"
  echo "Configurando empresa, armazéns, PDV e usuário dono..."
  docker compose run --rm -T \
    -e EMPRESA_NOME -e EMPRESA_CNPJ -e EMPRESA_CIDADE -e EMPRESA_MODO -e COZINHA_NOME -e COZINHA_CNPJ \
    -e ODOO_ADMIN_USER_PASSWORD -e BOTECO_HOSTNAME -e REDE_CLIENTES -e REDE_SISTEMA \
    odoo odoo shell -c /etc/odoo/odoo.conf -d "$BOTECO_DB" --no-http --workers=0 --logfile= \
    < scripts/configurar_empresa.py
else
  echo "Banco '${BOTECO_DB}' já existe. Atualizando módulos boteco_*..."
  instalar_modulos -u "$MODULOS_BOTECO"
fi

# -----------------------------------------------------------------------------
passo "5/6 Subindo o sistema"
docker compose up -d
echo -n "Aguardando o Odoo responder"
for i in $(seq 1 90); do
  if curl -fsk "https://localhost/web/health" >/dev/null 2>&1; then echo " pronto."; break; fi
  echo -n "."; sleep 2
  [[ $i -eq 90 ]] && falha "o Odoo não respondeu. Veja: docker compose logs odoo"
done

# -----------------------------------------------------------------------------
passo "6/6 Agendamentos (backup na nuvem, atualização pela tela e reinício automático)"
if [[ $E_LINUX -eq 1 && $MODO_DEV -eq 0 ]]; then
  cat > /etc/systemd/system/boteco-backup-nuvem.service <<EOF
[Unit]
Description=Backup diário do Boteco na nuvem (criptografado)
After=docker.service
[Service]
Type=oneshot
WorkingDirectory=${RAIZ}
ExecStart=/bin/bash ${RAIZ}/scripts/backup-nuvem.sh
EOF
  cat > /etc/systemd/system/boteco-backup-nuvem.timer <<EOF
[Unit]
Description=Agenda o backup diário do Boteco na nuvem
[Timer]
OnCalendar=*-*-* 07:30:00
Persistent=true
[Install]
WantedBy=timers.target
EOF
  # Atualização pela tela (Configuração > Atualizar sistema). Roda como root, igual a esta instalação
  # (precisa ler o .env e usar o Docker). Atualizar à mão no servidor: sudo ./scripts/atualizar.sh --git
  # Sem chmod nos scripts: o git veria a mudança de permissão como alteração local e travaria o "git pull"
  cat > /etc/systemd/system/boteco-atualizacao.service <<EOF
[Unit]
Description=Boteco: atende o pedido da tela "Atualizar sistema"
After=docker.service
[Service]
Type=oneshot
WorkingDirectory=${RAIZ}
ExecStart=/bin/bash ${RAIZ}/scripts/agente_atualizacao.sh processar
TimeoutStartSec=3600
EOF
  cat > /etc/systemd/system/boteco-atualizacao.path <<EOF
[Unit]
Description=Boteco: vigia pedidos da tela "Atualizar sistema"
[Path]
PathExists=${RAIZ}/atualizacao/pedido.txt
Unit=boteco-atualizacao.service
[Install]
WantedBy=multi-user.target
EOF
  cat > /etc/systemd/system/boteco-atualizacao-verificar.service <<EOF
[Unit]
Description=Boteco: procura atualizações no GitHub
After=network-online.target
[Service]
Type=oneshot
WorkingDirectory=${RAIZ}
ExecStart=/bin/bash ${RAIZ}/scripts/agente_atualizacao.sh verificar
EOF
  cat > /etc/systemd/system/boteco-atualizacao-verificar.timer <<EOF
[Unit]
Description=Boteco: procura atualizações no GitHub a cada 3 horas
[Timer]
OnBootSec=5min
OnUnitActiveSec=3h
[Install]
WantedBy=timers.target
EOF
  systemctl daemon-reload
  systemctl enable --now boteco-backup-nuvem.timer >/dev/null
  systemctl enable --now boteco-atualizacao.path boteco-atualizacao-verificar.timer >/dev/null
  echo "Backup na nuvem agendado para 07:30 (depois do fechamento)."
  echo "Atualização pela tela ativada (o servidor procura novidades no GitHub a cada 3 horas)."
else
  echo "Modo desenvolvimento: agendamento do host não instalado."
fi

FIM=$(date +%s)
echo -e "\n${VERDE}Pronto em $(( (FIM-INICIO)/60 )) min $(( (FIM-INICIO)%60 )) s.${NORMAL}"
echo "  Acesse:         https://${BOTECO_HOSTNAME:-boteco.local}   (ou https://localhost)"
echo "  Login por PIN:  https://${BOTECO_HOSTNAME:-boteco.local}/boteco/pin"
echo "  Saúde:          https://${BOTECO_HOSTNAME:-boteco.local}/boteco/saude"
echo "  Usuário dono:   admin  (senha em .env -> ODOO_ADMIN_USER_PASSWORD; troque no 1º acesso)"
