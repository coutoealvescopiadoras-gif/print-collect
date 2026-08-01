#!/bin/zsh

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
ENV_FILE="$ROOT_DIR/web/.env"

cat > "$ENV_FILE" <<'EOF'
VITE_API_URL=https://api.minhaempresa.com.br
EOF

echo "Frontend configurado para usar a API publica em https://api.minhaempresa.com.br"
