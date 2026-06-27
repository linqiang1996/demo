#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
API_KEY="${RENDER_API_KEY:-}"
OWNER_ID="${RENDER_OWNER_ID:-${1:-}}"
REPO_URL="${RENDER_REPO_URL:-${2:-}}"

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

PAYLOAD_FILE="$(mktemp)"
cleanup() {
  rm -f "$PAYLOAD_FILE"
}
trap cleanup EXIT

export ROOT_DIR OWNER_ID REPO_URL PAYLOAD_FILE
python3 - <<'PY'
import json
import os
from pathlib import Path


def load_env(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        return values
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip()
    return values


root_dir = Path(os.environ["ROOT_DIR"])
env = load_env(root_dir / ".env")

service_name = os.getenv("RENDER_SERVICE_NAME", "fof-nav-tracker")
root_subdir = os.getenv("RENDER_ROOT_DIR", "").strip()
branch = os.getenv("RENDER_BRANCH", "").strip()
plan = os.getenv("RENDER_PLAN", "starter")
region = os.getenv("RENDER_REGION", "").strip()
disk_enabled = os.getenv("RENDER_ENABLE_DISK", "true").strip().lower() in {"1", "true", "yes", "on"}

db_path = "/opt/render/project/src/data/fof_nav.db" if disk_enabled else "/tmp/fof_nav.db"

payload = {
    "type": "web_service",
    "name": service_name,
    "ownerId": os.environ["OWNER_ID"],
    "repo": os.environ["REPO_URL"],
    "autoDeploy": "yes",
    "envVars": [
        {"key": "FOF_SECRET_KEY", "generateValue": True},
        {"key": "FOF_DB_PATH", "value": db_path},
        {"key": "FOF_BOOTSTRAP_SAMPLES", "value": "false"},
        {"key": "FOF_MAIL_PROVIDER", "value": env.get("FOF_MAIL_PROVIDER", "qq")},
        {"key": "FOF_MAIL_ADDRESS", "value": env.get("FOF_MAIL_ADDRESS", "")},
        {"key": "FOF_MAIL_PASSWORD", "value": env.get("FOF_MAIL_PASSWORD", "")},
        {"key": "FOF_MAIL_IMAP_HOST", "value": env.get("FOF_MAIL_IMAP_HOST", "imap.qq.com")},
        {"key": "FOF_MAIL_IMAP_PORT", "value": env.get("FOF_MAIL_IMAP_PORT", "993")},
        {"key": "FOF_MAIL_FOLDER", "value": env.get("FOF_MAIL_FOLDER", "INBOX")},
        {"key": "FOF_MAIL_SEARCH_KEYWORD", "value": env.get("FOF_MAIL_SEARCH_KEYWORD", "净值")},
        {"key": "FOF_MAIL_POLL_MINUTES", "value": env.get("FOF_MAIL_POLL_MINUTES", "5")},
        {"key": "FOF_MAIL_USE_SSL", "value": env.get("FOF_MAIL_USE_SSL", "true")},
        {"key": "FOF_MAIL_INITIAL_SYNC_LIMIT", "value": env.get("FOF_MAIL_INITIAL_SYNC_LIMIT", "300")},
        {"key": "FOF_MAIL_OVERLAP_UIDS", "value": env.get("FOF_MAIL_OVERLAP_UIDS", "300")},
        {"key": "FOF_RISK_FREE_RATE", "value": env.get("FOF_RISK_FREE_RATE", "0.015")},
        {"key": "FOF_ANNUAL_TRADING_DAYS", "value": env.get("FOF_ANNUAL_TRADING_DAYS", "252")},
        {"key": "FOF_WEEKLY_PERIODS", "value": env.get("FOF_WEEKLY_PERIODS", "52")},
    ],
    "serviceDetails": {
        "runtime": "docker",
        "plan": plan,
        "healthCheckPath": "/healthz",
    },
}

if root_subdir:
    payload["rootDir"] = root_subdir
if branch:
    payload["branch"] = branch
if region:
    payload["serviceDetails"]["region"] = region
if disk_enabled:
    payload["serviceDetails"]["disk"] = {
        "name": "fof-nav-data",
        "mountPath": "/opt/render/project/src/data",
        "sizeGB": 5,
    }

access_code = env.get("FOF_ACCESS_CODE", "").strip()
if access_code:
    payload["envVars"].append({"key": "FOF_ACCESS_CODE", "value": access_code})

Path(os.environ["PAYLOAD_FILE"]).write_text(
    json.dumps(payload, ensure_ascii=False),
    encoding="utf-8",
)
PY

HTTP_CODE="$(
  curl -sS -o /tmp/render-create-response.json -w '%{http_code}' https://api.render.com/v1/services \
    -H "Accept: application/json" \
    -H "Content-Type: application/json" \
    -H "Authorization: Bearer $API_KEY" \
    --data @"$PAYLOAD_FILE"
)"

cat /tmp/render-create-response.json
echo
echo "HTTP $HTTP_CODE"

if [[ "$HTTP_CODE" != "201" ]]; then
  exit 1
fi
