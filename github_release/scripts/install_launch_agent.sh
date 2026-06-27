#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
AGENT_DIR="$HOME/Library/LaunchAgents"
PLIST_FILE="$AGENT_DIR/com.fof.tracker.local.plist"
PYTHON_BIN="$(command -v python3)"

mkdir -p "$AGENT_DIR"

cat > "$PLIST_FILE" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>com.fof.tracker.local</string>
  <key>ProgramArguments</key>
  <array>
    <string>$PYTHON_BIN</string>
    <string>$ROOT_DIR/scripts/run_server.py</string>
  </array>
  <key>WorkingDirectory</key>
  <string>$ROOT_DIR</string>
  <key>RunAtLoad</key>
  <true/>
  <key>KeepAlive</key>
  <true/>
  <key>StandardOutPath</key>
  <string>$ROOT_DIR/runtime/launchd.log</string>
  <key>StandardErrorPath</key>
  <string>$ROOT_DIR/runtime/launchd.log</string>
</dict>
</plist>
PLIST

mkdir -p "$ROOT_DIR/runtime"
launchctl unload "$PLIST_FILE" >/dev/null 2>&1 || true
launchctl load "$PLIST_FILE"
echo "已安装开机自启动守护：$PLIST_FILE"
echo "重启电脑后会自动拉起 FOF 服务"
