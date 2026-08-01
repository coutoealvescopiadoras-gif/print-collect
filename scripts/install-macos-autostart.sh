#!/bin/zsh

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
LAUNCH_AGENTS_DIR="$HOME/Library/LaunchAgents"
LOG_DIR="$ROOT_DIR/logs"
SERVER_PLIST="$LAUNCH_AGENTS_DIR/com.printcollect.server.plist"
WEB_PLIST="$LAUNCH_AGENTS_DIR/com.printcollect.web.plist"
LAUNCH_DOMAIN="gui/$(id -u)"
SERVER_LABEL="com.printcollect.server"
WEB_LABEL="com.printcollect.web"

mkdir -p "$LAUNCH_AGENTS_DIR" "$LOG_DIR"

bootout_existing_agent() {
  local plist_path="$1"
  local label="$2"
  launchctl bootout "$LAUNCH_DOMAIN/$label" >/dev/null 2>&1 || true
  launchctl bootout "$LAUNCH_DOMAIN" "$plist_path" >/dev/null 2>&1 || true
  launchctl unload "$plist_path" >/dev/null 2>&1 || true
}

zsh "$ROOT_DIR/scripts/use-local-api.sh"

bootout_existing_agent "$SERVER_PLIST" "$SERVER_LABEL"
bootout_existing_agent "$WEB_PLIST" "$WEB_LABEL"
zsh "$ROOT_DIR/scripts/stop-local.sh" >/dev/null 2>&1 || true
sleep 2

cat > "$SERVER_PLIST" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>com.printcollect.server</string>
  <key>ProgramArguments</key>
  <array>
    <string>/bin/zsh</string>
    <string>-lc</string>
    <string>zsh "$ROOT_DIR/scripts/start-server.sh"</string>
  </array>
  <key>WorkingDirectory</key>
  <string>$ROOT_DIR</string>
  <key>RunAtLoad</key>
  <true/>
  <key>KeepAlive</key>
  <true/>
  <key>StandardOutPath</key>
  <string>$LOG_DIR/server.log</string>
  <key>StandardErrorPath</key>
  <string>$LOG_DIR/server-error.log</string>
</dict>
</plist>
EOF

cat > "$WEB_PLIST" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>com.printcollect.web</string>
  <key>ProgramArguments</key>
  <array>
    <string>/bin/zsh</string>
    <string>-lc</string>
    <string>zsh "$ROOT_DIR/scripts/start-web.sh"</string>
  </array>
  <key>WorkingDirectory</key>
  <string>$ROOT_DIR</string>
  <key>RunAtLoad</key>
  <true/>
  <key>KeepAlive</key>
  <true/>
  <key>StandardOutPath</key>
  <string>$LOG_DIR/web.log</string>
  <key>StandardErrorPath</key>
  <string>$LOG_DIR/web-error.log</string>
</dict>
</plist>
EOF

load_agent() {
  local plist_path="$1"
  launchctl bootout "$LAUNCH_DOMAIN" "$plist_path" >/dev/null 2>&1 || true
  launchctl bootstrap "$LAUNCH_DOMAIN" "$plist_path" >/dev/null 2>&1 || launchctl load "$plist_path"
  launchctl enable "$LAUNCH_DOMAIN/$(/usr/libexec/PlistBuddy -c 'Print :Label' "$plist_path")" >/dev/null 2>&1 || true
  launchctl kickstart -k "$LAUNCH_DOMAIN/$(/usr/libexec/PlistBuddy -c 'Print :Label' "$plist_path")" >/dev/null 2>&1 || true
}

load_agent "$SERVER_PLIST"
load_agent "$WEB_PLIST"

echo "Inicializacao automatica do Print Collect ativada."
echo "Painel: http://localhost:5173"
echo "API: http://localhost:8000"
