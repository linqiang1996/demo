#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
OUTPUT_DIR="$ROOT_DIR/runtime/package"
ARCHIVE="$ROOT_DIR/runtime/fof_local_bundle.tar.gz"

rm -rf "$OUTPUT_DIR"
mkdir -p "$OUTPUT_DIR"

cp -R "$ROOT_DIR/app" "$OUTPUT_DIR/"
cp -R "$ROOT_DIR/miniprogram" "$OUTPUT_DIR/"
cp -R "$ROOT_DIR/scripts" "$OUTPUT_DIR/"
cp "$ROOT_DIR"/README.md "$ROOT_DIR"/requirements.txt "$ROOT_DIR"/wsgi.py "$ROOT_DIR"/fof净值.py "$OUTPUT_DIR/"
cp "$ROOT_DIR"/.env.example "$OUTPUT_DIR/"

tar -czf "$ARCHIVE" -C "$OUTPUT_DIR" .
echo "已打包: $ARCHIVE"
