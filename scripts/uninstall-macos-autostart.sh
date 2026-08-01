#!/bin/zsh

set -euo pipefail

LAUNCH_AGENTS_DIR="$HOME/Library/LaunchAgents"
SERVER_PLIST="$LAUNCH_AGENTS_DIR/com.printcollect.server.plist"
WEB_PLIST="$LAUNCH_AGENTS_DIR/com.printcollect.web.plist"
LAUNCH_DOMAIN="gui/$(id -u)"

unload_agent() {
  local plist_path="$1"
  local label=""
  if [[ -f "$plist_path" ]]; then
    label="$(/usr/libexec/PlistBuddy -c 'Print :Label' "$plist_path" 2>/dev/null || true)"
  fi
  if [[ -n "$label" ]]; then
    launchctl bootout "$LAUNCH_DOMAIN/$label" >/dev/null 2>&1 || launchctl bootout "$LAUNCH_DOMAIN" "$plist_path" >/dev/null 2>&1 || true
    launchctl disable "$LAUNCH_DOMAIN/$label" >/dev/null 2>&1 || true
  fi
  launchctl unload "$plist_path" >/dev/null 2>&1 || true
}

unload_agent "$SERVER_PLIST"
unload_agent "$WEB_PLIST"

rm -f "$SERVER_PLIST" "$WEB_PLIST"

echo "Inicializacao automatica do Print Collect desativada."
