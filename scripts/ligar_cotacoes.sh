#!/usr/bin/env bash
# Liga os serviços opcionais da Etapa 35 no servidor:
#   ./scripts/ligar_cotacoes.sh whatsapp   -> Evolution API (WhatsApp do bar por QR Code)
#   ./scripts/ligar_cotacoes.sh coletor    -> coletor de ofertas de sites e Instagram
# Gera as chaves no .env (se faltarem), passa para o Odoo e sobe o contêiner. Pode rodar de novo sem problema.
set -Eeuo pipefail
export MSYS_NO_PATHCONV=1
cd "$(dirname "$0")/.."
QUAL="${1:-}"
set -a; # shellcheck disable=SC1091
source .env; set +a
DB="${BOTECO_DB:-boteco}"

no_env() {  # no_env NOME VALOR: grava/atualiza a variável no .env
  if grep -q "^$1=" .env; then sed -i "s|^$1=.*|$1=$2|" .env; else echo "$1=$2" >> .env; fi
}

odoo_shell() {
  docker compose exec -T odoo odoo shell -c /etc/odoo/odoo.conf -d "$DB" --no-http --logfile= 2>/dev/null
}

case "$QUAL" in
  whatsapp)
    if [[ -z "${EVOLUTION_API_KEY:-}" ]]; then
      EVOLUTION_API_KEY="$(openssl rand -hex 24)"
      no_env EVOLUTION_API_KEY "$EVOLUTION_API_KEY"
      echo "==> Chave do Evolution API criada no .env"
    fi
    docker compose exec -T db psql -U "${POSTGRES_USER:-odoo}" -d postgres -tc \
      "SELECT 1 FROM pg_database WHERE datname='evolution'" | grep -q 1 || \
      docker compose exec -T db createdb -U "${POSTGRES_USER:-odoo}" evolution
    docker compose --profile whatsapp up -d evolution
    printf '%s\n' \
      "P = env['ir.config_parameter'].sudo()" \
      "P.set_param('boteco.evolution_url', 'http://evolution:8080')" \
      "P.set_param('boteco.evolution_apikey', '${EVOLUTION_API_KEY}')" \
      "P.set_param('boteco.evolution_webhook_base', 'http://odoo:8069')" \
      "env.cr.commit()" | odoo_shell
    echo "Pronto. No Odoo: Configuração › Sistema › WhatsApp (conectar) › Conectar WhatsApp."
    ;;
  coletor)
    TOKEN="$(printf '%s\n' "print('TOKEN=' + env['boteco.cotacoes']._token('boteco.cotacoes_token_coletor'))" "env.cr.commit()" \
      | odoo_shell | sed -n 's/^TOKEN=//p' | tail -1)"
    [[ -n "$TOKEN" ]] || { echo "Não consegui ler o token do coletor no Odoo (o módulo boteco_cotacoes está instalado?)"; exit 1; }
    no_env BOTECO_COLETOR_TOKEN "$TOKEN"
    docker compose --profile coletor up -d --build coletor
    echo "Pronto. Horários em Compras › WhatsApp e coletor. Log: docker compose logs -f coletor"
    ;;
  *)
    echo "Uso: $0 whatsapp|coletor"; exit 2 ;;
esac
