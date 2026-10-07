#!/usr/bin/env bash
# Atualiza o sistema com um comando: backup antes, atualização dos módulos e volta automática se falhar.
#
#   ./scripts/atualizar.sh                -> atualiza os módulos boteco_* (código já copiado/git pull)
#   ./scripts/atualizar.sh --git          -> faz git pull antes
#   ./scripts/atualizar.sh --imagem       -> também baixa a imagem odoo:18 mais nova (correções do Odoo)
#
# Faça fora do horário de funcionamento: o sistema fica fora do ar por alguns minutos.
set -Eeuo pipefail
export MSYS_NO_PATHCONV=1
cd "$(dirname "$0")/.."
set -a; # shellcheck disable=SC1091
source .env; set +a
DB="${BOTECO_DB:-boteco}"
MODULOS="boteco_base,boteco_cardapio,boteco_pos,boteco_kds,boteco_autoatendimento,boteco_estoque,boteco_cozinha_central,boteco_b2b,boteco_painel,boteco_fiscal_export"

for arg in "$@"; do
  case "$arg" in
    --git) git pull --ff-only ;;
    --imagem) docker compose pull odoo ;;
  esac
done

echo "==> 1/4 Backup antes de atualizar"
docker compose exec -T backup bash /usr/local/bin/backup-loop.sh --uma-vez
DUMP="$(ls -1t "${BACKUP_DIR:-./backups}"/boteco-*.dump | head -1)"
echo "    guardado: $DUMP"

echo "==> 2/4 Parando o Odoo"
docker compose stop odoo

echo "==> 3/4 Atualizando módulos"
LOG="$(mktemp)"
if docker compose run --rm -T odoo odoo -c /etc/odoo/odoo.conf -d "$DB" --workers=0 -u "$MODULOS" \
     --stop-after-init --logfile= > "$LOG" 2>&1 && ! grep -qE " (ERROR|CRITICAL) " "$LOG"; then
  echo "==> 4/4 Subindo de novo"
  docker compose up -d odoo
  echo "Atualizado com sucesso."
else
  echo "FALHOU. Trecho do log:"
  grep -E " (ERROR|CRITICAL) " -A15 "$LOG" | tail -40
  echo "==> Voltando o backup de antes (volta automática)"
  yes RESTAURAR | ./scripts/restaurar.sh "$DUMP"
  echo "Sistema voltou para como estava antes. Log completo: $LOG"
  exit 1
fi
