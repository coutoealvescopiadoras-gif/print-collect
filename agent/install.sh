#!/bin/bash
# Instala o coletor Print Collect no Linux/macOS
set -e

INSTALL_DIR="${PRINT_COLLECT_DIR:-/opt/print-collect}"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

echo "=== Print Collect Agent — Instalação ==="
echo "Diretório: $INSTALL_DIR"

sudo mkdir -p "$INSTALL_DIR"
sudo cp -r "$SCRIPT_DIR/print_collect" "$INSTALL_DIR/"
sudo cp "$SCRIPT_DIR/pyproject.toml" "$INSTALL_DIR/"
sudo cp "$SCRIPT_DIR/config.example.yaml" "$INSTALL_DIR/config.yaml"

cd "$INSTALL_DIR"
python3 -m venv .venv
source .venv/bin/activate
pip install -q --upgrade pip
pip install -q .

if [ ! -f "$INSTALL_DIR/config.yaml" ]; then
  echo "Edite $INSTALL_DIR/config.yaml antes de iniciar."
fi

echo ""
echo "Instalação concluída!"
echo ""
echo "Próximos passos:"
echo "  1. sudo nano $INSTALL_DIR/config.yaml"
echo "  2. $INSTALL_DIR/.venv/bin/print-collect --test"
echo "  3. $INSTALL_DIR/.venv/bin/print-collect --once"
echo "  4. sudo cp $SCRIPT_DIR/print-collect.service /etc/systemd/system/"
echo "  5. sudo systemctl enable --now print-collect"
echo ""
