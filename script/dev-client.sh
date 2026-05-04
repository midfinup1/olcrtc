#!/bin/bash
set -euo pipefail

PROVIDER="${PROVIDER:-wbstream}"
ROOM_ID="${ROOM_ID:?ROOM_ID is required}"
KEY="${KEY:?KEY is required}"
SOCKS_HOST="${SOCKS_HOST:-127.0.0.1}"
SOCKS_PORT="${SOCKS_PORT:-8808}"
DNS="${DNS:-1.1.1.1:53}"
DATA_DIR="${DATA_DIR:-data}"

go build -o olcrtc cmd/olcrtc/main.go

exec ./olcrtc \
    -mode cnc \
    -provider "$PROVIDER" \
    -id "$ROOM_ID" \
    -key "$KEY" \
    -dns "$DNS" \
    -data "$DATA_DIR" \
    -socks-host "$SOCKS_HOST" \
    -socks-port "$SOCKS_PORT"
