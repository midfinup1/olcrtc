#!/bin/bash

set -euo pipefail

APP_NAME="BareBone VPN"
ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"

cd "$ROOT_DIR"

echo "=== BareBoneVPN macOS release build ==="
echo "Root: $ROOT_DIR"
echo ""

if ! command -v go >/dev/null 2>&1; then
    echo "[X] Go is not installed"
    exit 1
fi

if ! command -v python3 >/dev/null 2>&1; then
    echo "[X] Python3 is not installed"
    exit 1
fi

echo "[*] Cleaning old build..."
rm -rf build
rm -rf dist
rm -f app/BareBoneVPN

find . -name ".DS_Store" -delete

echo "[*] Preparing Python venv..."

if [ ! -d ".venv" ]; then
    python3 -m venv .venv
fi

source .venv/bin/activate

python -m pip install --upgrade pip
pip install -r app/requirements.txt pyinstaller

echo "[*] Building BareBoneVPN binary..."
go build -o app/BareBoneVPN cmd/barebone/main.go

if [ ! -f "app/BareBoneVPN" ]; then
    echo "[X] app/BareBoneVPN was not created"
    exit 1
fi

chmod +x app/BareBoneVPN

echo "[*] Building macOS app..."

pyinstaller \
    --clean \
    --windowed \
    --name "$APP_NAME" \
    --add-binary "app/BareBoneVPN:." \
    --paths app \
    app/app_standalone.py

APP_PATH="dist/$APP_NAME.app"

if [ ! -d "$APP_PATH" ]; then
    echo "[X] App was not created: $APP_PATH"
    exit 1
fi

echo "[*] Signing app with ad-hoc signature..."
codesign --force --deep --sign - "$APP_PATH"

echo "[*] Creating zip..."
cd dist
rm -f "$APP_NAME.zip"
ditto -c -k --sequesterRsrc --keepParent "$APP_NAME.app" "$APP_NAME.zip"

echo ""
echo "[+] Done"
echo "App: dist/$APP_NAME.app"
echo "Zip: dist/$APP_NAME.zip"