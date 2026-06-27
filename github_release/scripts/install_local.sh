#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

python3 -m pip install -r requirements.txt
chmod +x scripts/start_local.sh scripts/stop_local.sh scripts/status_local.sh scripts/install_local.sh scripts/package_local.sh
echo "依赖安装完成"
echo "启动命令: ./scripts/start_local.sh"
