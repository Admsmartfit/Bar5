#!/usr/bin/env bash
# Backup automático do Boteco (roda dentro do contêiner "backup", imagem postgres:16).
#
#   - A cada BACKUP_INTERVALO_MIN minutos: banco (pg_dump formato custom) + arquivos (filestore)
#   - Guarda BACKUP_RETENCAO_DIAS dias no disco de backup (/backups)
#   - Escreve /backups/ultimo_backup.json (a página /boteco/saude mostra)
#
#   backup-loop.sh            -> fica em laço (serviço)
#   backup-loop.sh --uma-vez  -> faz um backup agora e sai (usado pelo atualizar.sh)
set -uo pipefail

DB="${BOTECO_DB:-boteco}"
DESTINO="${BACKUP_DESTINO:-/backups}"
RETENCAO="${BACKUP_RETENCAO_DIAS:-30}"
INTERVALO="${BACKUP_INTERVALO_MIN:-60}"
FILESTORE="/var/lib/odoo/filestore/${DB}"

status() {
  # status ok|erro tamanho mensagem arquivo
  printf '{"data": "%s", "status": "%s", "tamanho_bytes": %s, "erro": "%s", "arquivo": "%s"}\n' \
    "$(date -u +%Y-%m-%dT%H:%M:%S+00:00)" "$1" "${2:-0}" "${3:-}" "${4:-}" > "${DESTINO}/ultimo_backup.json.tmp"
  mv "${DESTINO}/ultimo_backup.json.tmp" "${DESTINO}/ultimo_backup.json"
}

um_backup() {
  local carimbo base dump tar tamanho
  carimbo="$(date +%Y%m%d-%H%M)"
  base="${DESTINO}/boteco-${carimbo}"
  dump="${base}.dump"
  tar="${base}-arquivos.tar.gz"
  mkdir -p "$DESTINO"

  if ! pg_dump -Fc -Z 6 -d "$DB" -f "${dump}.parcial" 2> "${base}.erro"; then
    status erro 0 "$(tr -d '"\n' < "${base}.erro" | cut -c1-200)"
    rm -f "${dump}.parcial" "${base}.erro"
    return 1
  fi
  mv "${dump}.parcial" "$dump"
  if [[ -d "$FILESTORE" ]]; then
    tar -czf "${tar}.parcial" -C "$(dirname "$FILESTORE")" "$(basename "$FILESTORE")" 2>> "${base}.erro" \
      && mv "${tar}.parcial" "$tar"
  fi
  rm -f "${base}.erro"
  tamanho=$(stat -c %s "$dump")
  if [[ -f "$tar" ]]; then
    tamanho=$(( tamanho + $(stat -c %s "$tar") ))
  fi
  status ok "$tamanho" "" "$(basename "$dump")"
  # Retenção: apaga o que passou do prazo
  find "$DESTINO" -maxdepth 1 -name 'boteco-*' -type f -mtime "+${RETENCAO}" -delete
  echo "[backup] $(date '+%d/%m %H:%M') ok: $(basename "$dump") ($((tamanho / 1024 / 1024)) MB)"
}

if [[ "${1:-}" == "--uma-vez" ]]; then
  um_backup
  exit $?
fi

echo "[backup] serviço iniciado: a cada ${INTERVALO} min, guarda ${RETENCAO} dias em ${DESTINO}"
# Espera o banco existir (primeira instalação)
until psql -d "$DB" -c 'select 1' >/dev/null 2>&1; do sleep 30; done
while true; do
  um_backup || echo "[backup] FALHOU – veja ${DESTINO}/ultimo_backup.json"
  sleep $(( INTERVALO * 60 ))
done
