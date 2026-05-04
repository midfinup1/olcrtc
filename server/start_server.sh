#!/bin/bash

set -euo pipefail

WORK_DIR="/root/olcrtc"
CONTAINER_NAME="olcrtc-server"
IMAGE_NAME="docker.io/library/golang:1.26-alpine"

PROVIDER="${PROVIDER:-wbstream}"
LINK_TYPE="direct"
TRANSPORT_TYPE="datachannel"
DNS_SERVER="${DNS_SERVER:-1.1.1.1:53}"
DATA_DIR="/app/data"

CONNECTION_FILE="$WORK_DIR/connection.env"
MAIL_SENDER="$WORK_DIR/server/mail_config_sender.py"
LOG_FILE="$WORK_DIR/server-start.log"

KEY_FILE="$WORK_DIR/server/key.hex"

mkdir -p "$WORK_DIR/server"
mkdir -p "$WORK_DIR/data"

echo "==================================================" >> "$LOG_FILE"
echo "start-server.sh started at $(date -Is)" >> "$LOG_FILE"

cd "$WORK_DIR"

if [ ! -f "$WORK_DIR/go.mod" ]; then
    echo "[X] go.mod not found in $WORK_DIR" | tee -a "$LOG_FILE"
    exit 1
fi

if [ ! -f "$KEY_FILE" ]; then
    openssl rand -hex 32 > "$KEY_FILE"
    chmod 600 "$KEY_FILE"
fi

KEY="$(cat "$KEY_FILE" | tr -d '\n\r ')"

PREVIOUS_ROOM_ID=""

if [ -f "$CONNECTION_FILE" ]; then
    PREVIOUS_ROOM_ID="$(grep '^ROOM_ID=' "$CONNECTION_FILE" | cut -d '=' -f2- | tr -d '"' || true)"
fi

echo "[*] Previous room: $PREVIOUS_ROOM_ID" >> "$LOG_FILE"

echo "[*] Stopping old container..." >> "$LOG_FILE"
podman stop "$CONTAINER_NAME" >> "$LOG_FILE" 2>&1 || true
podman rm "$CONTAINER_NAME" >> "$LOG_FILE" 2>&1 || true

echo "[*] Pulling Go image..." >> "$LOG_FILE"
podman pull "$IMAGE_NAME" >> "$LOG_FILE" 2>&1

echo "[*] Building olcRTC..." >> "$LOG_FILE"
podman run --rm \
    -v "$WORK_DIR:/app" \
    -w /app \
    "$IMAGE_NAME" \
    sh -c "go build -o olcrtc cmd/olcrtc/main.go" >> "$LOG_FILE" 2>&1

if [ ! -f "$WORK_DIR/olcrtc" ]; then
    echo "[X] Build failed: $WORK_DIR/olcrtc not found" | tee -a "$LOG_FILE"
    exit 1
fi

echo "[*] Starting olcRTC server..." >> "$LOG_FILE"

podman run -d \
    --name "$CONTAINER_NAME" \
    --restart unless-stopped \
    --network host \
    -v "$WORK_DIR:/app" \
    -w /app \
    "$IMAGE_NAME" \
    ./olcrtc \
        -mode srv \
        -link "$LINK_TYPE" \
        -transport "$TRANSPORT_TYPE" \
        -provider "$PROVIDER" \
        -key "$KEY" \
        -data "$DATA_DIR" \
        -dns "$DNS_SERVER" >> "$LOG_FILE" 2>&1

echo "[*] Waiting for room creation..." >> "$LOG_FILE"

ACTUAL_ROOM_ID=""

for i in $(seq 1 60); do
    LOGS="$(podman logs "$CONTAINER_NAME" 2>&1 || true)"

    if [ "$PROVIDER" = "wbstream" ]; then
        ACTUAL_ROOM_ID="$(echo "$LOGS" | grep -Eo 'WB Stream room created: [^ ]+' | tail -n 1 | awk '{print $5}' || true)"
    fi

    if [ "$PROVIDER" = "jazz" ]; then
        ACTUAL_ROOM_ID="$(echo "$LOGS" | grep -Eo 'Jazz room created: [^ ]+' | tail -n 1 | awk '{print $4}' || true)"
    fi

    if [ -n "$ACTUAL_ROOM_ID" ]; then
        break
    fi

    sleep 1
done

if [ -z "$ACTUAL_ROOM_ID" ]; then
    echo "[X] Could not extract room ID from logs" | tee -a "$LOG_FILE"
    echo "[*] Full logs:" >> "$LOG_FILE"
    podman logs "$CONTAINER_NAME" >> "$LOG_FILE" 2>&1 || true
    exit 1
fi

echo "[*] Actual room: $ACTUAL_ROOM_ID" >> "$LOG_FILE"

cat > "$CONNECTION_FILE" <<EOF
PROVIDER="$PROVIDER"
ROOM_ID="$ACTUAL_ROOM_ID"
ENCRYPTION_KEY="$KEY"
TRANSPORT_TYPE="$TRANSPORT_TYPE"
DNS_SERVER="$DNS_SERVER"
EOF

chmod 600 "$CONNECTION_FILE"

echo "[+] connection.env updated" >> "$LOG_FILE"

if [ "$PREVIOUS_ROOM_ID" != "$ACTUAL_ROOM_ID" ]; then
    echo "[*] Room changed. Sending config by email..." >> "$LOG_FILE"

    if [ -x "$MAIL_SENDER" ]; then
        python3 "$MAIL_SENDER" >> "$LOG_FILE" 2>&1 || echo "[!] Failed to send email config" >> "$LOG_FILE"
    else
        echo "[!] Mail sender not found or not executable: $MAIL_SENDER" >> "$LOG_FILE"
    fi
else
    echo "[*] Room unchanged. Email sending skipped." >> "$LOG_FILE"
fi

echo "[+] Server started successfully" >> "$LOG_FILE"
echo "Provider: $PROVIDER" >> "$LOG_FILE"
echo "Room ID: $ACTUAL_ROOM_ID" >> "$LOG_FILE"
echo "Transport: $TRANSPORT_TYPE" >> "$LOG_FILE"
echo "DNS: $DNS_SERVER" >> "$LOG_FILE"

echo "[+] Server started successfully"
echo "Provider: $PROVIDER"
echo "Room ID: $ACTUAL_ROOM_ID"
echo "Transport: $TRANSPORT_TYPE"
echo "Connection file: $CONNECTION_FILE"