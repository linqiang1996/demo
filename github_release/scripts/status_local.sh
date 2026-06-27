#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
PID_FILE="$ROOT_DIR/runtime/fof.pid"
LOG_FILE="$ROOT_DIR/runtime/fof.log"

if [[ -f "$PID_FILE" ]]; then
  PID="$(cat "$PID_FILE" 2>/dev/null || true)"
  if [[ -n "${PID:-}" ]] && kill -0 "$PID" 2>/dev/null; then
    echo "FOF 服务运行中，PID: $PID"
    echo "访问地址: http://127.0.0.1:5050"
    exit 0
  fi
fi

PORT_PID="$(lsof -tiTCP:5050 -sTCP:LISTEN 2>/dev/null | head -n 1 || true)"
if [[ -n "${PORT_PID:-}" ]]; then
  echo "FOF 服务运行中，PID: $PORT_PID"
  echo "访问地址: http://127.0.0.1:5050"
  exit 0
fi

echo "FOF 服务未运行"
if [[ -f "$LOG_FILE" ]]; then
  echo "最近日志:"
  tail -n 20 "$LOG_FILE"
fi
