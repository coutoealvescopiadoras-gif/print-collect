#!/bin/zsh

set -euo pipefail

export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin:$PATH"

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
SERVER_DIR="$ROOT_DIR/server"

cd "$SERVER_DIR"

recreate_venv() {
  rm -rf ".venv"
  python3 -m venv .venv
}

if [[ ! -x ".venv/bin/python" ]]; then
  recreate_venv
fi

source .venv/bin/activate
python3 -m pip install --upgrade pip
if ! pip install -r requirements.txt; then
  recreate_venv
  source .venv/bin/activate
  python3 -m pip install --upgrade pip
  pip install -r requirements.txt
fi

python3 -c "import fastapi, sqlalchemy" >/dev/null

exec uvicorn app.main:app --host 0.0.0.0 --port 8000
