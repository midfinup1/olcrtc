#!/bin/bash
set -euo pipefail

PROVIDER="${PROVIDER:-wbstream}"
ROOM_ID="${ROOM_ID:-any}"
KEY_FILE="${HOME}/.olcrtc_key"
DNS="${DNS:-1.1.1.1:53}"
DATA_DIR="${DATA_DIR:-data}"

if [ ! -f "$KEY_FILE" ]; then
    openssl rand -hex 32 > "$KEY_FILE"
    chmod 600 "$KEY_FILE"
fi

KEY="$(cat "$KEY_FILE")"

go build -o olcrtc cmd/olcrtc/main.go

exec ./olcrtc \
    -mode srv \
    -provider "$PROVIDER" \
    -id "$ROOM_ID" \
    -key "$KEY" \
    -dns "$DNS" \
    -data "$DATA_DIR"
