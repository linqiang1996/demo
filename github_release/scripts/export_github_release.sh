#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
OUTPUT_DIR="$ROOT_DIR/runtime/github_release"

rm -rf "$OUTPUT_DIR"
mkdir -p "$OUTPUT_DIR"

cp -R "$ROOT_DIR/app" "$OUTPUT_DIR/"
cp -R "$ROOT_DIR/miniprogram" "$OUTPUT_DIR/"
cp -R "$ROOT_DIR/scripts" "$OUTPUT_DIR/"
cp -R "$ROOT_DIR/tests" "$OUTPUT_DIR/"

cp "$ROOT_DIR"/README.md "$OUTPUT_DIR/"
cp "$ROOT_DIR"/requirements.txt "$OUTPUT_DIR/"
cp "$ROOT_DIR"/wsgi.py "$OUTPUT_DIR/"
cp "$ROOT_DIR"/fof净值.py "$OUTPUT_DIR/"
cp "$ROOT_DIR"/Dockerfile "$OUTPUT_DIR/"
cp "$ROOT_DIR"/render.yaml "$OUTPUT_DIR/"
cp "$ROOT_DIR"/.env.example "$OUTPUT_DIR/"
cp "$ROOT_DIR"/.gitignore "$OUTPUT_DIR/"
cp "$ROOT_DIR"/.dockerignore "$OUTPUT_DIR/"

find "$OUTPUT_DIR" -name '__pycache__' -type d -prune -exec rm -rf {} +
find "$OUTPUT_DIR" -name '*.pyc' -delete
find "$OUTPUT_DIR" -name '*.pyo' -delete
find "$OUTPUT_DIR" -name '.DS_Store' -delete

rm -rf "$OUTPUT_DIR/runtime"
rm -rf "$OUTPUT_DIR/data"

echo "GitHub 发布目录已生成: $OUTPUT_DIR"
echo "这个目录可以直接作为 GitHub 仓库根目录内容。"
