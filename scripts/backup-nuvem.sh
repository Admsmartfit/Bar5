#!/usr/bin/env bash
# Backup diário na nuvem, CRIPTOGRAFADO (roda no host pelo agendamento do systemd, 07:30).
#
# Pega o backup local mais recente (banco + arquivos), criptografa com GPG (AES256, senha do .env)
# e envia com o rclone para BACKUP_NUVEM_DESTINO (ex.: gdrive:boteco-backup). Guarda 30 dias lá.
# Configure o rclone uma vez com:  rclone config
set -Eeuo pipefail
cd "$(dirname "$0")/.."
set -a; # shellcheck disable=SC1091
source .env; set +a

DESTINO="${BACKUP_NUVEM_DESTINO:-}"
[[ -n "$DESTINO" ]] || { echo "BACKUP_NUVEM_DESTINO vazio no .env: backup na nuvem desligado."; exit 0; }
[[ -n "${BACKUP_NUVEM_SENHA:-}" ]] || { echo "ERRO: defina BACKUP_NUVEM_SENHA no .env (o backup vai criptografado)."; exit 1; }
command -v rclone >/dev/null || { echo "ERRO: instale o rclone (curl https://rclone.org/install.sh | sudo bash)."; exit 1; }
command -v gpg >/dev/null || { echo "ERRO: instale o gnupg (sudo apt install gnupg)."; exit 1; }

PASTA="${BACKUP_DIR:-./backups}"
DUMP="$(ls -1t "$PASTA"/boteco-*.dump 2>/dev/null | head -1 || true)"
[[ -n "$DUMP" ]] || { echo "ERRO: nenhum backup local em $PASTA"; exit 1; }
ARQUIVOS="${DUMP%.dump}-arquivos.tar.gz"

TEMP="$(mktemp -d)"
trap 'rm -rf "$TEMP"' EXIT
PACOTE="$TEMP/$(basename "${DUMP%.dump}").tar"
tar -cf "$PACOTE" -C "$PASTA" "$(basename "$DUMP")" $( [[ -f "$ARQUIVOS" ]] && basename "$ARQUIVOS" )
gpg --batch --yes --pinentry-mode loopback --passphrase "$BACKUP_NUVEM_SENHA" \
    --symmetric --cipher-algo AES256 -o "$PACOTE.gpg" "$PACOTE"

rclone copy "$PACOTE.gpg" "$DESTINO" --retries 5
rclone delete "$DESTINO" --min-age 30d --include 'boteco-*.tar.gpg' || true
echo "Backup na nuvem enviado: $(basename "$PACOTE").gpg -> $DESTINO"

# Para restaurar da nuvem:
#   rclone copy DESTINO/boteco-AAAAMMDD-HHMM.tar.gpg .
#   gpg -d boteco-AAAAMMDD-HHMM.tar.gpg > pacote.tar && tar -xf pacote.tar
#   ./scripts/restaurar.sh boteco-AAAAMMDD-HHMM.dump
