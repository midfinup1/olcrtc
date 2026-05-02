#!/bin/bash

echo "ЕСЛИ У ВАС ЕСТЬ ПРОБЛЕМЫ - Я В КУРСЕ, ПРОЕКТ В БЕТЕ, ПО ПРОБЛЕМАМ В ЧАТ t.me/openlibrecommunity ИЛИ ВООБЩЕ НЕКУДА, ЖДИТЕ РЕЛИЗА"

set -e

CONTAINER_NAME="olcrtc-client"
IMAGE_NAME="docker.io/library/golang:1.26-alpine"
WORK_DIR="$(cd "$(dirname "$0")/.." && pwd)"

SOCKS_IP="127.0.0.1"
SOCKS_PORT="8808"

BRANCH="master"
LINK_TYPE="direct"
TRANSPORT_TYPE="datachannel"
DATA_DIR="/app/data"
DNS_SERVER="1.1.1.1:53"

while [[ $# -gt 0 ]]; do
    case $1 in
        --branch=*)
            BRANCH="${1#*=}"
            shift
            ;;
        *)
            shift
            ;;
    esac
done

echo "=== OlcRTC Client Deployment Script ==="
echo ""
echo "[*] Using branch: $BRANCH"
echo "[*] Using workspace: $WORK_DIR"
echo ""

if ! command -v podman &> /dev/null; then
    echo "[X] Podman is not installed."
    echo "Install Podman Desktop or install Podman manually:"
    echo "  brew install podman"
    echo "  podman machine init"
    echo "  podman machine start"
    exit 1
fi

echo "[+] Using Podman"

if ! podman info &> /dev/null; then
    echo "[X] Podman is installed, but Podman machine is not running."
    echo "Run:"
    echo "  podman machine start"
    exit 1
fi

echo "[+] Podman machine is running"
echo ""

if [ ! -f "$WORK_DIR/go.mod" ]; then
    echo "[X] go.mod not found in workspace:"
    echo "  $WORK_DIR"
    echo "Run this script from inside the olcRTC project or keep it inside ./script/"
    exit 1
fi

echo "[*] Checking local modules..."

if [ ! -f "$WORK_DIR/internal/transport/videochannel/gr/go.mod" ]; then
    echo "[!] Missing local module:"
    echo "    internal/transport/videochannel/gr/go.mod"
    echo "[*] Trying to initialize git submodules..."

    git -C "$WORK_DIR" submodule update --init --recursive

    if [ ! -f "$WORK_DIR/internal/transport/videochannel/gr/go.mod" ]; then
        echo "[X] Local module is still missing after submodule initialization."
        echo "Check that repository contains submodule:"
        echo "  internal/transport/videochannel/gr"
        exit 1
    fi
fi

echo "[+] Local modules are OK"
echo ""

echo "Select provider:"
echo "  1) telemost"
echo "  2) jazz"
echo "  3) wbstream"
read -p "Enter choice [1-3, default: 1]: " PROVIDER_CHOICE

case "$PROVIDER_CHOICE" in
    2)
        PROVIDER="jazz"
        ;;
    3)
        PROVIDER="wbstream"
        ;;
    *)
        PROVIDER="telemost"
        ;;
esac

echo "[*] Using provider: $PROVIDER"
echo ""

if [ "$PROVIDER" = "jazz" ]; then
    read -p "Enter Room ID (format: roomId:password from server): " ROOM_ID

    if [ -z "$ROOM_ID" ]; then
        echo "[X] Room ID cannot be empty"
        exit 1
    fi
else
    read -p "Enter Room ID: " ROOM_ID

    if [ -z "$ROOM_ID" ]; then
        echo "[X] Room ID cannot be empty"
        exit 1
    fi
fi

echo ""
read -p "Enter Encryption Key (hex): " KEY

if [ -z "$KEY" ]; then
    echo "[X] Encryption key cannot be empty"
    exit 1
fi

echo ""
read -p "SOCKS5 listen ip on your Mac [default: 127.0.0.1]: " IP_INPUT
SOCKS_IP=${IP_INPUT:-127.0.0.1}

echo ""
read -p "SOCKS5 listen port on your Mac [default: 8808]: " PORT_INPUT
SOCKS_PORT=${PORT_INPUT:-8808}

echo ""
echo "[*] Stopping old instance..."
podman stop "$CONTAINER_NAME" 2>/dev/null || true
podman rm "$CONTAINER_NAME" 2>/dev/null || true

echo "[*] Pulling Go image..."
podman pull "$IMAGE_NAME"

echo "[*] Building OlcRTC..."
podman run --rm \
    -v "$WORK_DIR:/app" \
    -w /app \
    "$IMAGE_NAME" \
    sh -c "go build -o olcrtc cmd/olcrtc/main.go"

if [ ! -f "$WORK_DIR/olcrtc" ]; then
    echo "[X] Build failed"
    exit 1
fi

echo "[*] Starting OlcRTC client..."

podman run -d \
    --name "$CONTAINER_NAME" \
    --restart unless-stopped \
    -p "$SOCKS_IP:$SOCKS_PORT:$SOCKS_PORT" \
    -v "$WORK_DIR:/app" \
    -w /app \
    "$IMAGE_NAME" \
    ./olcrtc \
        -mode cnc \
        -link "$LINK_TYPE" \
        -transport "$TRANSPORT_TYPE" \
        -provider "$PROVIDER" \
        -id "$ROOM_ID" \
        -key "$KEY" \
        -data "$DATA_DIR" \
        -dns "$DNS_SERVER" \
        -socks-port "$SOCKS_PORT" \
        -socks-host 0.0.0.0

sleep 2

echo ""
echo "[+] Client started successfully!"
echo ""
echo "Container name: $CONTAINER_NAME"
echo "Provider:       $PROVIDER"
echo "Room ID:        $ROOM_ID"
echo "SOCKS5 proxy:   $SOCKS_IP:$SOCKS_PORT"
echo "Link:           $LINK_TYPE"
echo "Transport:      $TRANSPORT_TYPE"
echo "Data dir:       $DATA_DIR"
echo "DNS:            $DNS_SERVER"
echo ""
echo "View logs:"
echo "  podman logs -f $CONTAINER_NAME"
echo ""
echo "Stop client:"
echo "  podman stop $CONTAINER_NAME"
echo ""
echo "Test proxy:"
echo "  export all_proxy=socks5h://$SOCKS_IP:$SOCKS_PORT"
echo "  curl -fsSL https://ifconfig.me"
echo ""