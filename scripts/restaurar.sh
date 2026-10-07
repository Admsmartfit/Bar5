#!/usr/bin/env bash
# Restaura um backup com um comando (meta do PRD: menos de 30 minutos num PC limpo).
#
#   ./scripts/restaurar.sh                                  -> o backup mais recente da pasta de backup
#   ./scripts/restaurar.sh /mnt/backup/boteco-20261007-2300.dump
#   BANCO=boteco_teste ./scripts/restaurar.sh arquivo.dump  -> restaura em outro banco (teste mensal)
#
# Num PC limpo: copie o projeto + .env, rode ./instalar.sh e depois este script.
set -Eeuo pipefail
export MSYS_NO_PATHCONV=1
cd "$(dirname "$0")/.."
set -a; # shellcheck disable=SC1091
source .env; set +a

BANCO="${BANCO:-${BOTECO_DB:-boteco}}"
PASTA="${BACKUP_DIR:-./backups}"
DUMP="${1:-$(ls -1t "$PASTA"/boteco-*.dump 2>/dev/null | head -1 || true)}"
[[ -f "$DUMP" ]] || { echo "ERRO: backup não encontrado: ${DUMP:-'(nenhum)'}"; exit 1; }
ARQUIVOS="${DUMP%.dump}-arquivos.tar.gz"
INICIO=$(date +%s)

echo "==> Restaurando $(basename "$DUMP") no banco '$BANCO'"
if [[ "$BANCO" == "${BOTECO_DB:-boteco}" ]]; then
  read -r -p "Isto APAGA o banco atual '$BANCO'. Digite RESTAURAR para continuar: " ok
  [[ "$ok" == "RESTAURAR" ]] || { echo "Cancelado."; exit 1; }
  docker compose stop odoo >/dev/null
fi

docker compose up -d db >/dev/null
for _ in $(seq 1 30); do docker compose exec -T db pg_isready -U "$POSTGRES_USER" >/dev/null 2>&1 && break; sleep 1; done
docker compose exec -T db dropdb -U "$POSTGRES_USER" --if-exists "$BANCO"
docker compose exec -T db createdb -U "$POSTGRES_USER" -O "$POSTGRES_USER" "$BANCO"
# Lê o dump pela entrada padrão (por isso sem -j: restauração paralela exige arquivo)
if ! docker compose exec -T db pg_restore -U "$POSTGRES_USER" -d "$BANCO" --no-owner --role="$POSTGRES_USER" \
     --exit-on-error < "$DUMP"; then
  echo "ERRO: a restauração do banco falhou."
  exit 1
fi
USUARIOS="$(docker compose exec -T db psql -U "$POSTGRES_USER" -d "$BANCO" -tAc "select count(*) from res_users" | tr -d '[:space:]')"
[[ "$USUARIOS" =~ ^[0-9]+$ && "$USUARIOS" -gt 0 ]] || { echo "ERRO: o banco restaurado está vazio."; exit 1; }

if [[ -f "$ARQUIVOS" ]]; then
  echo "==> Restaurando arquivos (fotos, anexos)"
  docker compose run --rm -T --entrypoint sh -u 0 odoo -c \
    "mkdir -p /var/lib/odoo/filestore && rm -rf /var/lib/odoo/filestore/$BANCO && \
     tar -xzf - -C /var/lib/odoo/filestore && \
     [ \"\$(ls /var/lib/odoo/filestore | grep -c ${BOTECO_DB:-boteco})\" -ge 1 ] && \
     ( [ '$BANCO' = '${BOTECO_DB:-boteco}' ] || cp -r /var/lib/odoo/filestore/${BOTECO_DB:-boteco} /var/lib/odoo/filestore/$BANCO ) ; \
     chown -R odoo:odoo /var/lib/odoo/filestore" < "$ARQUIVOS"
fi

if [[ "$BANCO" == "${BOTECO_DB:-boteco}" ]]; then
  docker compose up -d odoo >/dev/null
fi
FIM=$(date +%s)
echo "Restaurado em $(( (FIM - INICIO) / 60 )) min $(( (FIM - INICIO) % 60 )) s."
