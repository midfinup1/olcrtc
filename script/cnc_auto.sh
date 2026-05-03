#!/bin/bash

set -e

CONFIG_URL="http://194.58.58.92:8090/connection.json"
CONFIG_TOKEN="3311fe77453c1f36d1ad8535470681595c7bf019cf7831a1797e9ce863932973"

CONTAINER_NAME="olcrtc-client"
IMAGE_NAME="docker.io/library/golang:1.26-alpine"
WORK_DIR="$(cd "$(dirname "$0")/.." && pwd)"

SOCKS_IP="127.0.0.1"
SOCKS_PORT="8808"

LINK_TYPE="direct"
DATA_DIR="/app/data"

VIDEO_W="1080"
VIDEO_H="1080"
VIDEO_FPS="10"
VIDEO_BITRATE="1000k"
VIDEO_CODEC="tile"
VIDEO_HW="none"

echo "=== olcRTC HTTP Auto Client ==="
echo "[*] Workspace: $WORK_DIR"
echo "[*] Config URL: $CONFIG_URL"
echo ""

if ! command -v podman &> /dev/null; then
    echo "[X] Podman is not installed"
    exit 1
fi

if ! podman info &> /dev/null; then
    echo "[X] Podman machine is not running"
    echo "Run:"
    echo "  podman machine start"
    exit 1
fi

if [ ! -f "$WORK_DIR/go.mod" ]; then
    echo "[X] go.mod not found in $WORK_DIR"
    exit 1
fi

echo "[*] Fetching connection data..."

CONNECTION_JSON=$(curl -fsSL \
    -H "Authorization: Bearer $CONFIG_TOKEN" \
    "$CONFIG_URL")

PROVIDER=$(python3 -c 'import sys,json; print(json.load(sys.stdin)["provider"])' <<< "$CONNECTION_JSON")
ROOM_ID=$(python3 -c 'import sys,json; print(json.load(sys.stdin)["room_id"])' <<< "$CONNECTION_JSON")
ENCRYPTION_KEY=$(python3 -c 'import sys,json; print(json.load(sys.stdin)["encryption_key"])' <<< "$CONNECTION_JSON")
TRANSPORT_TYPE=$(python3 -c 'import sys,json; print(json.load(sys.stdin)["transport_type"])' <<< "$CONNECTION_JSON")
DNS_SERVER=$(python3 -c 'import sys,json; print(json.load(sys.stdin).get("dns_server", "1.1.1.1:53"))' <<< "$CONNECTION_JSON")

if [ -z "$PROVIDER" ] || [ -z "$ROOM_ID" ] || [ -z "$ENCRYPTION_KEY" ] || [ -z "$TRANSPORT_TYPE" ]; then
    echo "[X] connection.json is incomplete"
    exit 1
fi

echo "[+] Loaded:"
echo "Provider:       $PROVIDER"
echo "Room ID:        $ROOM_ID"
echo "Transport:      $TRANSPORT_TYPE"
echo "DNS:            $DNS_SERVER"
echo ""

echo "[*] Checking local modules..."

if [ ! -f "$WORK_DIR/internal/transport/videochannel/gr/go.mod" ]; then
    git -C "$WORK_DIR" submodule update --init --recursive
fi

if [ ! -f "$WORK_DIR/internal/transport/videochannel/gr/go.mod" ]; then
    echo "[X] Missing internal/transport/videochannel/gr/go.mod"
    exit 1
fi

echo "[*] Stopping old client..."
podman stop "$CONTAINER_NAME" 2>/dev/null || true
podman rm "$CONTAINER_NAME" 2>/dev/null || true

echo "[*] Pulling Go image..."
podman pull "$IMAGE_NAME"

echo "[*] Building olcRTC..."
podman run --rm \
    -v "$WORK_DIR:/app" \
    -w /app \
    "$IMAGE_NAME" \
    sh -c "go build -o olcrtc cmd/olcrtc/main.go"

if [ ! -f "$WORK_DIR/olcrtc" ]; then
    echo "[X] Build failed"
    exit 1
fi

OLCRTC_ARGS=(
    -mode cnc
    -link "$LINK_TYPE"
    -transport "$TRANSPORT_TYPE"
    -provider "$PROVIDER"
    -id "$ROOM_ID"
    -key "$ENCRYPTION_KEY"
    -data "$DATA_DIR"
    -dns "$DNS_SERVER"
)

if [ "$TRANSPORT_TYPE" = "videochannel" ]; then
    OLCRTC_ARGS+=(
        -video-w "$VIDEO_W"
        -video-h "$VIDEO_H"
        -video-fps "$VIDEO_FPS"
        -video-bitrate "$VIDEO_BITRATE"
        -video-codec "$VIDEO_CODEC"
        -video-hw "$VIDEO_HW"
    )
fi

OLCRTC_ARGS+=(
    -socks-port "$SOCKS_PORT"
    -socks-host 0.0.0.0
)

echo "[*] Starting olcRTC client..."

if [ "$TRANSPORT_TYPE" = "videochannel" ]; then
    podman run -d \
        --name "$CONTAINER_NAME" \
        --restart unless-stopped \
        -p "$SOCKS_IP:$SOCKS_PORT:$SOCKS_PORT" \
        -v "$WORK_DIR:/app" \
        -w /app \
        "$IMAGE_NAME" \
        sh -c 'apk add --no-cache ffmpeg ca-certificates git openssl >/dev/null && ./olcrtc "$@"' -- "${OLCRTC_ARGS[@]}"
else
    podman run -d \
        --name "$CONTAINER_NAME" \
        --restart unless-stopped \
        -p "$SOCKS_IP:$SOCKS_PORT:$SOCKS_PORT" \
        -v "$WORK_DIR:/app" \
        -w /app \
        "$IMAGE_NAME" \
        ./olcrtc "${OLCRTC_ARGS[@]}"
fi

sleep 2

echo ""
echo "[+] Client started"
echo "SOCKS5:    $SOCKS_IP:$SOCKS_PORT"
echo "Provider:  $PROVIDER"
echo "Room ID:   $ROOM_ID"
echo "Transport: $TRANSPORT_TYPE"
echo ""
echo "Test:"
echo "  curl --max-time 20 -v --socks5-hostname $SOCKS_IP:$SOCKS_PORT https://ifconfig.me"