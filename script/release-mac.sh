#!/bin/bash
set -euo pipefail

APP_NAME="olcRTC Manager"
ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"

cd "$ROOT_DIR"

if [ ! -d .venv ]; then
    python3 -m venv .venv
fi

source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r app/requirements.txt pyinstaller

go build -o app/olcrtc cmd/olcrtc/main.go

pyinstaller \
    --clean \
    --windowed \
    --name "$APP_NAME" \
    --add-binary "app/olcrtc:." \
    app/app_standalone.py

codesign --force --deep --sign - "dist/$APP_NAME.app"

cd dist
ditto -c -k --sequesterRsrc --keepParent "$APP_NAME.app" "$APP_NAME.zip"

echo "Done: $ROOT_DIR/dist/$APP_NAME.zip"
