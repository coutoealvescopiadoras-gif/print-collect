#!/bin/zsh

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
LOG_DIR="$ROOT_DIR/logs"

mkdir -p "$LOG_DIR"

cleanup_stale_pid() {
  local pid_file="$1"
  if [[ -f "$pid_file" ]]; then
    local pid
    pid="$(cat "$pid_file" 2>/dev/null || true)"
    if [[ -z "$pid" ]] || ! kill -0 "$pid" >/dev/null 2>&1; then
      rm -f "$pid_file"
    fi
  fi
}

is_port_listening() {
  local port="$1"
  lsof -nP -iTCP:"$port" -sTCP:LISTEN >/dev/null 2>&1
}

detect_lan_ip() {
  local ip=""
  for iface in en0 en1; do
    ip="$(ipconfig getifaddr "$iface" 2>/dev/null || true)"
    if [[ -n "$ip" ]]; then
      echo "$ip"
      return 0
    fi
  done

  ip="$(ifconfig | awk '/inet / && $2 != "127.0.0.1" {print $2; exit}')"
  if [[ -n "$ip" ]]; then
    echo "$ip"
  fi
}

zsh "$ROOT_DIR/scripts/use-local-api.sh" >/dev/null

cleanup_stale_pid "$LOG_DIR/server.pid"
cleanup_stale_pid "$LOG_DIR/web.pid"

if [[ -f "$LOG_DIR/server.pid" ]] && kill -0 "$(cat "$LOG_DIR/server.pid")" >/dev/null 2>&1; then
  echo "Backend ja esta rodando (PID $(cat "$LOG_DIR/server.pid"))."
elif is_port_listening 8000; then
  echo "Backend ja esta respondendo na porta 8000."
else
  nohup zsh "$ROOT_DIR/scripts/start-server.sh" > "$LOG_DIR/server.log" 2> "$LOG_DIR/server-error.log" &
  echo $! > "$LOG_DIR/server.pid"
  echo "Backend iniciado (PID $(cat "$LOG_DIR/server.pid"))."
fi

if [[ -f "$LOG_DIR/web.pid" ]] && kill -0 "$(cat "$LOG_DIR/web.pid")" >/dev/null 2>&1; then
  echo "Frontend ja esta rodando (PID $(cat "$LOG_DIR/web.pid"))."
elif is_port_listening 5173; then
  echo "Frontend ja esta respondendo na porta 5173."
else
  nohup zsh "$ROOT_DIR/scripts/start-web.sh" > "$LOG_DIR/web.log" 2> "$LOG_DIR/web-error.log" &
  echo $! > "$LOG_DIR/web.pid"
  echo "Frontend iniciado (PID $(cat "$LOG_DIR/web.pid"))."
fi

ok_server=0
ok_web=0
for _ in {1..25}; do
  if curl -fsS http://localhost:8000/health >/dev/null 2>&1; then
    ok_server=1
  fi
  if curl -fsS -I http://localhost:5173 >/dev/null 2>&1; then
    ok_web=1
  fi
  if [[ "$ok_server" -eq 1 && "$ok_web" -eq 1 ]]; then
    break
  fi
  sleep 1
done

echo "Painel: http://localhost:5173"
echo "API: http://localhost:8000"

LAN_IP="$(detect_lan_ip || true)"
if [[ -n "${LAN_IP:-}" ]]; then
  echo "Painel na rede: http://$LAN_IP:5173"
  echo "API na rede: http://$LAN_IP:8000"
fi

if [[ "$ok_server" -ne 1 ]]; then
  echo "ERRO: backend nao respondeu em http://localhost:8000/health"
  echo "Ultimas linhas do log:"
  tail -n 40 "$LOG_DIR/server-error.log" 2>/dev/null || true
fi

if [[ "$ok_web" -ne 1 ]]; then
  echo "ERRO: frontend nao respondeu em http://localhost:5173"
  echo "Ultimas linhas do log:"
  tail -n 40 "$LOG_DIR/web-error.log" 2>/dev/null || true
fi
