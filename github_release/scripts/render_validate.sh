#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
OWNER_ID="${RENDER_OWNER_ID:-${1:-}}"
API_KEY="${RENDER_API_KEY:-}"

if [[ -z "$API_KEY" ]]; then
  echo "缺少 RENDER_API_KEY"
  exit 1
fi

if [[ -z "$OWNER_ID" ]]; then
  echo "缺少 RENDER_OWNER_ID，可作为环境变量传入，或作为第一个参数传入"
  exit 1
fi

echo "开始校验 render.yaml ..."
curl -sS --fail-with-body https://api.render.com/v1/blueprints/validate \
  -H "Accept: application/json" \
  -H "Authorization: Bearer $API_KEY" \
  -F "ownerId=$OWNER_ID" \
  -F "file=@$ROOT_DIR/render.yaml"
echo
