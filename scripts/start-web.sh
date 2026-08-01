#!/bin/zsh

set -euo pipefail

export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin:$PATH"

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
WEB_DIR="$ROOT_DIR/web"

cd "$WEB_DIR"

install_deps() {
  if [[ -f "package-lock.json" ]]; then
    npm ci
  else
    npm install
  fi
}

if ! install_deps; then
  rm -rf node_modules
  install_deps
fi

exec npm run dev -- --host 0.0.0.0 --port 5173
