#!/usr/bin/env bash
# Modo treinamento: copia o banco real para "boteco_treino" e sobe um Odoo só para ele
# em https://boteco.local:8443. Nada do que se faz lá entra no caixa ou no estoque de verdade,
# e nada é impresso.
#
#   ./scripts/treinamento.sh          -> (re)cria o banco de treino com os dados de agora e liga
#   ./scripts/treinamento.sh parar    -> desliga o treino
#   ./scripts/treinamento.sh ligar    -> liga sem recriar (continua de onde parou)
set -Eeuo pipefail
export MSYS_NO_PATHCONV=1
cd "$(dirname "$0")/.."
set -a; # shellcheck disable=SC1091
source .env; set +a
TREINO="${BOTECO_DB:-boteco}_treino"

gerar_conf() {
  sed -e "s/^db_name = .*/db_name = ${TREINO}/" -e "s/^dbfilter = .*/dbfilter = ^${TREINO}\$/" \
      -e "s/^workers = .*/workers = 2/" -e "s#^logfile = .*#logfile = /var/log/odoo/treino.log#" \
      config/odoo.conf > config/odoo-treino.conf
  # Treino não precisa de log em arquivo próprio montado: usa a saída padrão
  sed -i "s#^logfile = .*#logfile =#" config/odoo-treino.conf
}

case "${1:-recriar}" in
  parar)
    docker compose --profile treino stop odoo-treino
    echo "Treino desligado."
    exit 0 ;;
  ligar)
    gerar_conf
    docker compose --profile treino up -d odoo-treino
    echo "Treino ligado: https://${BOTECO_HOSTNAME:-boteco.local}:8443"
    exit 0 ;;
esac

echo "==> Copiando o banco real para '${TREINO}'"
docker compose --profile treino stop odoo-treino >/dev/null 2>&1 || true
docker compose exec -T backup bash /usr/local/bin/backup-loop.sh --uma-vez
DUMP="$(ls -1t "${BACKUP_DIR:-./backups}"/boteco-*.dump | head -1)"
BANCO="$TREINO" ./scripts/restaurar.sh "$DUMP"

echo "==> Marcando como banco de treino"
gerar_conf
docker compose run --rm -T odoo odoo -c /etc/odoo/odoo.conf -d "$TREINO" --db-filter="^${TREINO}$" --workers=0 \
  -i boteco_treinamento --stop-after-init --logfile= | grep -E " (ERROR|CRITICAL) " || true

docker compose --profile treino up -d odoo-treino
echo "Pronto. Treino em https://${BOTECO_HOSTNAME:-boteco.local}:8443 (mesmos usuários e PINs)."
echo "Tudo lá é de mentira: faixa vermelha 'MODO TREINAMENTO' em todas as telas."
