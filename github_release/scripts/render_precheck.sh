#!/usr/bin/env bash
set -euo pipefail

API_KEY="${RENDER_API_KEY:-}"
OWNER_ID="${RENDER_OWNER_ID:-${1:-}}"
REPO_URL="${RENDER_REPO_URL:-${2:-}}"
ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"

if [[ -z "$API_KEY" ]]; then
  echo "缺少 RENDER_API_KEY"
  exit 1
fi

if [[ -z "$OWNER_ID" ]]; then
  echo "缺少 RENDER_OWNER_ID，可作为环境变量传入，或作为第一个参数传入"
  exit 1
fi

if [[ -z "$REPO_URL" ]]; then
  echo "缺少 RENDER_REPO_URL，可作为环境变量传入，或作为第二个参数传入"
  exit 1
fi

echo "[1/3] 检查 Render Workspace 是否可访问 ..."
curl -sS --fail-with-body "https://api.render.com/v1/owners/$OWNER_ID" \
  -H "Accept: application/json" \
  -H "Authorization: Bearer $API_KEY"
echo
echo

echo "[2/3] 检查 render.yaml 是否能通过 Blueprint 校验 ..."
curl -sS https://api.render.com/v1/blueprints/validate \
  -H "Accept: application/json" \
  -H "Authorization: Bearer $API_KEY" \
  -F "ownerId=$OWNER_ID" \
  -F "file=@$ROOT_DIR/render.yaml"
echo
echo

echo "[3/3] 检查仓库地址是否可被公开访问 ..."
curl -I -L --max-time 20 "$REPO_URL" || true
echo
echo
echo "预检查完成。"
