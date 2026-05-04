#!/bin/bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"

BIN_PATH="$ROOT_DIR/app/olcrtc"

MODE="srv"
LINK_TYPE="direct"
TRANSPORT_TYPE="datachannel"
PROVIDER="${PROVIDER:-wbstream}"
ROOM_ID="${ROOM_ID:-}"
KEY="${KEY:-}"
DNS_SERVER="${DNS_SERVER:-1.1.1.1:53}"
DATA_DIR="${DATA_DIR:-$ROOT_DIR/runtime-data}"
DEBUG="${DEBUG:-false}"

echo "=== olcRTC dev server ==="
echo "Root:      $ROOT_DIR"
echo "Provider:  $PROVIDER"
echo "Transport: $TRANSPORT_TYPE"
echo "DNS:       $DNS_SERVER"
echo ""

mkdir -p "$ROOT_DIR/app"
mkdir -p "$DATA_DIR"

if [ ! -f "$BIN_PATH" ]; then
    echo "[*] Building olcRTC..."
    go build -o "$BIN_PATH" "$ROOT_DIR/cmd/olcrtc/main.go"
fi

if [ -z "$KEY" ]; then
    KEY="$(openssl rand -hex 32)"
    echo "[*] Generated key:"
    echo "$KEY"
fi

ARGS=(
    -mode "$MODE"
    -link "$LINK_TYPE"
    -transport "$TRANSPORT_TYPE"
    -provider "$PROVIDER"
    -key "$KEY"
    -data "$DATA_DIR"
    -dns "$DNS_SERVER"
)

if [ -n "$ROOM_ID" ]; then
    ARGS+=(-id "$ROOM_ID")
fi

if [ "$DEBUG" = "true" ]; then
    ARGS+=(-debug)
fi

echo ""
echo "[*] Starting server..."
echo ""

"$BIN_PATH" "${ARGS[@]}"