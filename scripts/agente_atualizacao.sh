#!/usr/bin/env bash
# Agente de atualização do Boteco (roda no servidor Linux, FORA do Docker, via systemd).
#
# O Odoo não consegue se atualizar sozinho (teria que se parar e reiniciar). Então a tela
# "Configuração > Atualizar sistema" só grava um pedido na pasta compartilhada atualizacao/,
# e este agente faz o trabalho no servidor:
#
#   ./scripts/agente_atualizacao.sh verificar   -> git fetch e lista o que há de novo no GitHub
#   ./scripts/agente_atualizacao.sh processar   -> atende o pedido da tela (verificar ou atualizar)
#
# Instalado pelo ./instalar.sh: boteco-atualizacao.path (vigia o pedido) e
# boteco-atualizacao-verificar.timer (procura atualizações de tempos em tempos).
set -Euo pipefail
cd "$(dirname "$0")/.."
RAIZ="$(pwd)"
PASTA="$RAIZ/atualizacao"
GIT=(git -c "safe.directory=$RAIZ")
mkdir -p "$PASTA"

agora() { date '+%Y-%m-%d %H:%M:%S'; }

# Escreve um arquivo de forma atômica (a tela nunca lê arquivo pela metade)
gravar() {
  local destino="$1"; shift
  printf '%s\n' "$@" > "$destino.tmp" && chmod 644 "$destino.tmp" && mv -f "$destino.tmp" "$destino"
}

ramo() { "${GIT[@]}" rev-parse --abbrev-ref --symbolic-full-name '@{u}' 2>/dev/null || echo "origin/main"; }

verificar() {
  local erro
  if ! erro="$("${GIT[@]}" fetch --quiet 2>&1)"; then
    gravar "$PASTA/verificacao.txt" "erro" "$(agora)" "Não consegui acessar o GitHub: ${erro//$'\n'/ }"
    return 1
  fi
  local remoto; remoto="$(ramo)"
  # Formato: commit<TAB>data<TAB>assunto (uma linha por versão)
  "${GIT[@]}" log -1 --format='%h%x09%ci%x09%s' HEAD > "$PASTA/versao_atual.txt.tmp" \
    && mv -f "$PASTA/versao_atual.txt.tmp" "$PASTA/versao_atual.txt"
  "${GIT[@]}" log --format='%h%x09%ci%x09%s' "HEAD..$remoto" > "$PASTA/disponiveis.txt.tmp" \
    && mv -f "$PASTA/disponiveis.txt.tmp" "$PASTA/disponiveis.txt"
  local alterado=""
  if [[ -n "$("${GIT[@]}" status --porcelain --untracked-files=no)" ]]; then
    alterado="Há arquivos alterados direto no servidor: a atualização vai falhar até resolver (git status)."
  fi
  gravar "$PASTA/verificacao.txt" "ok" "$(agora)" "$remoto${alterado:+ | $alterado}"
  chmod 644 "$PASTA"/*.txt 2>/dev/null || true
}

atualizar() {
  local imagem="$1" quem="$2"
  local antes; antes="$("${GIT[@]}" rev-parse --short HEAD)"
  gravar "$PASTA/status.txt" "em_andamento" "$(agora)" "" "$antes" "" "$quem"
  local opcoes=(--git)
  [[ "$imagem" == "1" ]] && opcoes+=(--imagem)
  if bash scripts/atualizar.sh "${opcoes[@]}" > "$PASTA/ultimo.log.tmp" 2>&1; then
    resultado="ok"
  else
    resultado="falhou"
  fi
  mv -f "$PASTA/ultimo.log.tmp" "$PASTA/ultimo.log"; chmod 644 "$PASTA/ultimo.log"
  gravar "$PASTA/status.txt" "$resultado" "$(sed -n 2p "$PASTA/status.txt")" "$(agora)" \
    "$antes" "$("${GIT[@]}" rev-parse --short HEAD)" "$quem"
  verificar || true
}

processar() {
  local pedido="$PASTA/pedido.txt"
  [[ -f "$pedido" ]] || exit 0
  # pedido.txt (gravado pela tela): acao<NL>imagem(0/1)<NL>quem pediu
  local acao imagem quem
  acao="$(sed -n 1p "$pedido")"; imagem="$(sed -n 2p "$pedido")"; quem="$(sed -n 3p "$pedido")"
  rm -f "$pedido"
  case "$acao" in
    verificar) verificar ;;
    atualizar) atualizar "${imagem:-0}" "${quem:-?}" ;;
    *) echo "pedido desconhecido: $acao" >&2 ;;
  esac
}

case "${1:-processar}" in
  verificar) verificar ;;
  processar) processar ;;
  *) echo "uso: $0 [verificar|processar]" >&2; exit 2 ;;
esac
