#!/usr/bin/env bash
# Roda os testes automáticos dos módulos boteco_* num banco descartável.
#
#   ./scripts/testar.sh                       -> todos os módulos boteco_*
#   ./scripts/testar.sh boteco_base           -> só um módulo
#   MANTER=1 ./scripts/testar.sh boteco_pos   -> não apaga o banco no fim (para investigar)
#
# Usa o mesmo docker-compose do sistema, mas um banco separado (boteco_teste).
set -Eeuo pipefail
export MSYS_NO_PATHCONV=1  # Git Bash no Windows: não converter /etc/... em C:/...
cd "$(dirname "$0")/.."

[[ -f .env ]] || { echo "Rode ./instalar.sh --dev primeiro (precisa do .env)."; exit 1; }
set -a; # shellcheck disable=SC1091
source .env; set +a

TODOS="boteco_base,boteco_cardapio,boteco_pos,boteco_kds,boteco_autoatendimento,boteco_estoque,boteco_cozinha_central,boteco_b2b,boteco_painel,boteco_fiscal_export"
MODULOS="${1:-$TODOS}"
BANCO="${BANCO_TESTE:-boteco_teste}"
TAGS="${TAGS:-/boteco_base,/boteco_cardapio,/boteco_pos,/boteco_kds,/boteco_autoatendimento,/boteco_estoque,/boteco_cozinha_central,/boteco_b2b,/boteco_painel,/boteco_fiscal_export}"

docker compose up -d db >/dev/null
for _ in $(seq 1 30); do
  docker compose exec -T db pg_isready -U "$POSTGRES_USER" >/dev/null 2>&1 && break
  sleep 1
done
docker compose exec -T db dropdb -U "$POSTGRES_USER" --if-exists "$BANCO"

LOG="$(mktemp)"
set +e
docker compose run --rm -T odoo odoo -c /etc/odoo/odoo.conf -d "$BANCO" --db-filter=".*"   --workers=0 --max-cron-threads=0 --http-port=8079 --logfile=   --load-language=pt_BR --without-demo=all -i "$MODULOS"   --test-enable --test-tags="$TAGS" --stop-after-init > "$LOG" 2>&1
STATUS=$?
set -e
grep -E " (ERROR|CRITICAL) |FAIL:|ParseError|Error:|odoo.tests.stats|odoo.tests.result" "$LOG" | head -80 || true

if [[ -z "${MANTER:-}" ]]; then
  docker compose exec -T db dropdb -U "$POSTGRES_USER" --if-exists "$BANCO" || true
fi

if [[ $STATUS -ne 0 ]] || grep -qE " [0-9]+ (ERROR|CRITICAL) " "$LOG"; then
  echo "FALHOU (código $STATUS). Log completo em $LOG"
  exit 1
fi
echo "OK: testes passaram (log em $LOG)"
