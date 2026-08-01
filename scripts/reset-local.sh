#!/bin/zsh

set -euo pipefail

if [[ "${1:-}" != "--yes" ]]; then
  echo "Uso: zsh scripts/reset-local.sh --yes"
  echo "Isso vai apagar server/.venv e web/node_modules para recriar do zero."
  exit 1
fi

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"

zsh "$ROOT_DIR/scripts/stop-local.sh" >/dev/null 2>&1 || true

rm -rf "$ROOT_DIR/server/.venv"
rm -rf "$ROOT_DIR/web/node_modules"

echo "Reset concluido."
echo "Agora rode:"
echo "zsh scripts/start-local-detached.sh"
