#!/usr/bin/env bash
# Carrega dados de demonstração (produtos, mesas, usuários e PINs) no banco boteco.
set -Eeuo pipefail
export MSYS_NO_PATHCONV=1  # Git Bash no Windows: não converter /etc/... em C:/...
cd "$(dirname "$0")/.."

docker compose run --rm -T odoo odoo shell -c /etc/odoo/odoo.conf -d boteco --no-http < scripts/dados_exemplo.py
