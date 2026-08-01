#!/bin/zsh

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
ENV_FILE="$ROOT_DIR/web/.env"

cat > "$ENV_FILE" <<'EOF'
VITE_API_URL=http://localhost:8000
EOF

echo "Frontend configurado para usar a API local em http://localhost:8000"
