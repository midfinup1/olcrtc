#!/bin/bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"

echo "[*] Cleaning project..."

cd "$ROOT_DIR"

rm -rf build

rm -rf dist

rm -rf __MACOSX

rm -rf app/__pycache__

rm -rf app/*.spec

rm -rf .pytest_cache

find . -name ".DS_Store" -delete

find . -name "__pycache__" -type d -prune -exec rm -rf {} +

find . -name "*.pyc" -delete

echo "[+] Clean complete"