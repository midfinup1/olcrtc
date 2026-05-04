#!/bin/bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"

BIN_PATH="$ROOT_DIR/app/olcrtc"

MODE="cnc"
LINK_TYPE="direct"
TRANSPORT_TYPE="datachannel"
PROVIDER="${PROVIDER:-wbstream}"
ROOM_ID="${ROOM_ID:-}"
KEY="${KEY:-}"
DNS_SERVER="${DNS_SERVER:-1.1.1.1:53}"
DATA_DIR="${DATA_DIR:-$ROOT_DIR/runtime-data}"

SOCKS_HOST="${SOCKS_HOST:-127.0.0.1}"
SOCKS_PORT="${SOCKS_PORT:-8808}"

DEBUG="${DEBUG:-false}"

echo "=== olcRTC dev client ==="
echo "Root:      $ROOT_DIR"
echo "Provider:  $PROVIDER"
echo "Transport: $TRANSPORT_TYPE"
echo "SOCKS5:    $SOCKS_HOST:$SOCKS_PORT"
echo "DNS:       $DNS_SERVER"
echo ""

if [ -z "$ROOM_ID" ]; then
    echo "[X] ROOM_ID is required"
    echo "Example:"
    echo "  ROOM_ID='019...' KEY='...' PROVIDER=wbstream ./script/dev-client.sh"
    exit 1
fi

if [ -z "$KEY" ]; then
    echo "[X] KEY is required"
    echo "Example:"
    echo "  ROOM_ID='019...' KEY='...' PROVIDER=wbstream ./script/dev-client.sh"
    exit 1
fi

mkdir -p "$ROOT_DIR/app"
mkdir -p "$DATA_DIR"

if [ ! -f "$BIN_PATH" ]; then
    echo "[*] Building olcRTC..."
    go build -o "$BIN_PATH" "$ROOT_DIR/cmd/olcrtc/main.go"
fi

ARGS=(
    -mode "$MODE"
    -link "$LINK_TYPE"
    -transport "$TRANSPORT_TYPE"
    -provider "$PROVIDER"
    -id "$ROOM_ID"
    -key "$KEY"
    -data "$DATA_DIR"
    -dns "$DNS_SERVER"
    -socks-host "$SOCKS_HOST"
    -socks-port "$SOCKS_PORT"
)

if [ "$DEBUG" = "true" ]; then
    ARGS+=(-debug)
fi

echo "[*] Starting client..."
echo ""

"$BIN_PATH" "${ARGS[@]}"