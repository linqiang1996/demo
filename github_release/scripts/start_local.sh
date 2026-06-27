#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
RUNTIME_DIR="$ROOT_DIR/runtime"
PID_FILE="$RUNTIME_DIR/fof.pid"
LOG_FILE="$RUNTIME_DIR/fof.log"

mkdir -p "$RUNTIME_DIR"

if [[ -f "$PID_FILE" ]]; then
  OLD_PID="$(cat "$PID_FILE" 2>/dev/null || true)"
  if [[ -n "${OLD_PID:-}" ]] && kill -0 "$OLD_PID" 2>/dev/null; then
    if lsof -iTCP:5050 -sTCP:LISTEN -n -P 2>/dev/null | awk 'NR>1 {print $2}' | grep -qx "$OLD_PID"; then
      echo "FOF 服务已在运行，PID: $OLD_PID"
      echo "访问地址: http://127.0.0.1:5050"
      exit 0
    fi
    kill "$OLD_PID" 2>/dev/null || true
    sleep 1
  fi
  rm -f "$PID_FILE"
fi

PORT_PID="$(lsof -tiTCP:5050 -sTCP:LISTEN 2>/dev/null | head -n 1 || true)"
if [[ -n "${PORT_PID:-}" ]]; then
  kill "$PORT_PID" 2>/dev/null || true
  sleep 1
fi

cd "$ROOT_DIR"
nohup python3 scripts/run_server.py >>"$LOG_FILE" 2>&1 &
NEW_PID=$!
echo "$NEW_PID" > "$PID_FILE"

for _ in $(seq 1 12); do
  if kill -0 "$NEW_PID" 2>/dev/null && lsof -iTCP:5050 -sTCP:LISTEN -n -P >/dev/null 2>&1; then
    echo "FOF 服务启动成功，PID: $NEW_PID"
    echo "访问地址: http://127.0.0.1:5050"
    exit 0
  fi
  sleep 1
done

rm -f "$PID_FILE"

echo "FOF 服务启动失败，请查看日志: $LOG_FILE"
exit 1
