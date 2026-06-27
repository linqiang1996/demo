#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
PID_FILE="$ROOT_DIR/runtime/fof.pid"

if [[ ! -f "$PID_FILE" ]]; then
  echo "FOF 服务未运行"
  exit 0
fi

PID="$(cat "$PID_FILE" 2>/dev/null || true)"
if [[ -n "${PID:-}" ]] && kill -0 "$PID" 2>/dev/null; then
  kill "$PID"
  sleep 1
fi

PORT_PID="$(lsof -tiTCP:5050 -sTCP:LISTEN 2>/dev/null | head -n 1 || true)"
if [[ -n "${PORT_PID:-}" ]]; then
  kill "$PORT_PID" 2>/dev/null || true
  sleep 1
fi

rm -f "$PID_FILE"
echo "FOF 服务已停止"
