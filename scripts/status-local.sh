#!/bin/zsh

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
LOG_DIR="$ROOT_DIR/logs"

echo "API health:"
curl -fsS http://localhost:8000/health || echo "NAO OK"

echo "\nFrontend:"
curl -fsS -I http://localhost:5173 | head -n 1 || echo "NAO OK"

echo "\nPortas:"
lsof -nP -iTCP:8000 -sTCP:LISTEN || true
lsof -nP -iTCP:5173 -sTCP:LISTEN || true

echo "\nUltimos erros:"
tail -n 30 "$LOG_DIR/server-error.log" 2>/dev/null || true
tail -n 30 "$LOG_DIR/web-error.log" 2>/dev/null || true
