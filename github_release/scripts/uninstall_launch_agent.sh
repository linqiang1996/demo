#!/usr/bin/env bash
set -euo pipefail

PLIST_FILE="$HOME/Library/LaunchAgents/com.fof.tracker.local.plist"

launchctl unload "$PLIST_FILE" >/dev/null 2>&1 || true
rm -f "$PLIST_FILE"
echo "已移除开机自启动守护"
