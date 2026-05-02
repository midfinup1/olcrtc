#!/bin/bash

echo "ЕСЛИ У ВАС ЕСТЬ ПРОБЛЕМЫ - Я В КУРСЕ, ПРОЕКТ В БЕТЕ, ПО ПРОБЛЕМАМ В ЧАТ t.me/openlibrecommunity ИЛИ ВООБЩЕ НЕКУДА, ЖДИТЕ РЕЛИЗА"

set -e

CONTAINER_NAME="olcrtc-server"
IMAGE_NAME="docker.io/library/golang:1.26-alpine"
WORK_DIR="$(cd "$(dirname "$0")/.." && pwd)"

BRANCH="master"
LINK_TYPE="direct"
TRANSPORT_TYPE="datachannel"
DATA_DIR="/app/data"
DNS_SERVER="1.1.1.1:53"

VIDEO_W="1080"
VIDEO_H="1080"
VIDEO_FPS="10"
VIDEO_BITRATE="1000k"
VIDEO_CODEC="tile"
VIDEO_HW="none"

while [[ $# -gt 0 ]]; do
    case $1 in
        --branch=*)
            BRANCH="${1#*=}"
            shift
            ;;
        --transport=*)
            TRANSPORT_TYPE="${1#*=}"
            shift
            ;;
        *)
            shift
            ;;
    esac
done

echo "=== OlcRTC Server Deployment Script ==="
echo ""
echo "[*] Using branch: $BRANCH"
echo "[*] Using workspace: $WORK_DIR"
echo "[*] Using transport: $TRANSPORT_TYPE"
echo ""

if ! command -v podman &> /dev/null; then
    echo "[X] Podman is not installed."
    echo "Install Podman manually:"
    echo "  sudo apt update"
    echo "  sudo apt install -y podman"
    exit 1
fi

echo "[+] Using Podman"

if ! podman info &> /dev/null; then
    echo "[X] Podman is installed, but it is not working correctly."
    exit 1
fi

echo "[+] Podman is working"
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
    echo "Jazz room options:"
    echo "  1) Auto-generate new room (recommended)"
    echo "  2) Use specific room ID (enter roomId:password)"
    read -p "Enter choice [1-2, default: 1]: " JAZZ_CHOICE

    case "$JAZZ_CHOICE" in
        2)
            read -p "Enter Room ID (format: roomId:password): " ROOM_ID
            if [ -z "$ROOM_ID" ]; then
                echo "[X] Room ID cannot be empty"
                exit 1
            fi
            ;;
        *)
            ROOM_ID="any"
            echo "[*] Will auto-generate Jazz room"
            ;;
    esac
elif [ "$PROVIDER" = "wbstream" ]; then
    echo "WB Stream room options:"
    echo "  1) Auto-generate new room (recommended)"
    echo "  2) Use specific room ID"
    read -p "Enter choice [1-2, default: 1]: " WB_CHOICE

    case "$WB_CHOICE" in
        2)
            read -p "Enter Room ID: " ROOM_ID
            if [ -z "$ROOM_ID" ]; then
                echo "[X] Room ID cannot be empty"
                exit 1
            fi
            ;;
        *)
            ROOM_ID="any"
            echo "[*] Will auto-generate WB Stream room"
            ;;
    esac
else
    read -p "Enter Room ID: " ROOM_ID
    if [ -z "$ROOM_ID" ]; then
        echo "[X] Room ID cannot be empty"
        exit 1
    fi
fi

echo ""
read -p "Use SOCKS5 proxy for egress? (y/N): " USE_PROXY

EXTRA_ARGS=()

if [[ "$USE_PROXY" =~ ^[Yy]$ ]]; then
    echo ""
    echo "Use this only if the VPS itself must go through another external SOCKS5 proxy."
    echo "Usually on VPS you should answer N."
    echo ""

    read -p "Enter SOCKS5 proxy address: " PROXY_ADDR_INPUT
    SOCKS_PROXY_ADDR="$PROXY_ADDR_INPUT"

    if [ -z "$SOCKS_PROXY_ADDR" ]; then
        echo "[X] SOCKS5 proxy address cannot be empty"
        exit 1
    fi

    read -p "Enter SOCKS5 proxy port [default: 1080]: " PROXY_PORT_INPUT
    SOCKS_PROXY_PORT=${PROXY_PORT_INPUT:-1080}

    echo "[*] Will use SOCKS5 proxy: $SOCKS_PROXY_ADDR:$SOCKS_PROXY_PORT"

    EXTRA_ARGS+=(
        -socks-proxy "$SOCKS_PROXY_ADDR"
        -socks-proxy-port "$SOCKS_PROXY_PORT"
    )
fi

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

KEY_FILE="$HOME/.olcrtc_key"

if [ -f "$KEY_FILE" ]; then
    echo "[*] Loading existing encryption key..."
    KEY=$(cat "$KEY_FILE")
else
    echo "[*] Generating new encryption key..."
    KEY=$(openssl rand -hex 32)
    echo "$KEY" > "$KEY_FILE"
    chmod 600 "$KEY_FILE"

    echo ""
    echo "=========================================="
    echo "NEW ENCRYPTION KEY (saved to $KEY_FILE):"
    echo "$KEY"
    echo "=========================================="
    echo ""
fi

OLCRTC_ARGS=(
    -mode srv
    -link "$LINK_TYPE"
    -transport "$TRANSPORT_TYPE"
    -provider "$PROVIDER"
    -id "$ROOM_ID"
    -key "$KEY"
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

OLCRTC_ARGS+=("${EXTRA_ARGS[@]}")

echo "[*] Starting OlcRTC server..."

if [ "$TRANSPORT_TYPE" = "videochannel" ]; then
    podman run -d \
        --name "$CONTAINER_NAME" \
        --restart unless-stopped \
        --network host \
        -v "$WORK_DIR:/app" \
        -w /app \
        "$IMAGE_NAME" \
        sh -c 'apk add --no-cache ffmpeg ca-certificates git openssl >/dev/null && ./olcrtc "$@"' -- "${OLCRTC_ARGS[@]}"
else
    podman run -d \
        --name "$CONTAINER_NAME" \
        --restart unless-stopped \
        --network host \
        -v "$WORK_DIR:/app" \
        -w /app \
        "$IMAGE_NAME" \
        ./olcrtc "${OLCRTC_ARGS[@]}"
fi

sleep 3

ACTUAL_ROOM_ID="$ROOM_ID"

if [ "$PROVIDER" = "jazz" ] && [ "$ROOM_ID" = "any" ]; then
    echo "[*] Waiting for Jazz room creation..."
    sleep 2

    LOGS=$(podman logs "$CONTAINER_NAME" 2>&1)
    ACTUAL_ROOM_ID=$(echo "$LOGS" | grep -oE 'Jazz room created: [^[:space:]]+' | sed 's/Jazz room created: //' | head -1)

    if [ -z "$ACTUAL_ROOM_ID" ]; then
        echo "[!] WARNING: Could not extract Jazz room ID from logs"
        echo "[*] Full logs:"
        podman logs "$CONTAINER_NAME"
        ACTUAL_ROOM_ID="(check logs above)"
    else
        echo "[+] Jazz room created: $ACTUAL_ROOM_ID"
    fi
elif [ "$PROVIDER" = "wbstream" ] && [ "$ROOM_ID" = "any" ]; then
    echo "[*] Waiting for WB Stream room creation..."
    sleep 2

    LOGS=$(podman logs "$CONTAINER_NAME" 2>&1)
    ACTUAL_ROOM_ID=$(echo "$LOGS" | grep -oE 'WB Stream room created: [^[:space:]]+' | sed 's/WB Stream room created: //' | head -1)

    if [ -z "$ACTUAL_ROOM_ID" ]; then
        echo "[!] WARNING: Could not extract WB Stream room ID from logs"
        echo "[*] Full logs:"
        podman logs "$CONTAINER_NAME"
        ACTUAL_ROOM_ID="(check logs above)"
    else
        echo "[+] WB Stream room created: $ACTUAL_ROOM_ID"
    fi
fi

echo ""
echo "[+] Server started successfully!"
echo ""
echo "Container name: $CONTAINER_NAME"
echo "Provider:       $PROVIDER"
echo "Room ID:        $ACTUAL_ROOM_ID"
echo "Encryption key: $KEY"
echo "Link:           $LINK_TYPE"
echo "Transport:      $TRANSPORT_TYPE"
echo "Data dir:       $DATA_DIR"
echo "DNS:            $DNS_SERVER"

if [ "$TRANSPORT_TYPE" = "videochannel" ]; then
    echo "Video width:    $VIDEO_W"
    echo "Video height:   $VIDEO_H"
    echo "Video fps:      $VIDEO_FPS"
    echo "Video bitrate:  $VIDEO_BITRATE"
    echo "Video codec:    $VIDEO_CODEC"
    echo "Video hw:       $VIDEO_HW"
fi

if [ ${#EXTRA_ARGS[@]} -gt 0 ]; then
    echo "SOCKS5 proxy:   $SOCKS_PROXY_ADDR:$SOCKS_PROXY_PORT"
fi

echo ""
echo "Check network mode:"
echo "  podman inspect $CONTAINER_NAME --format '{{.HostConfig.NetworkMode}}'"
echo ""
echo "View logs:"
echo "  podman logs -f $CONTAINER_NAME"
echo ""
echo "Stop server:"
echo "  podman stop $CONTAINER_NAME"
echo ""
echo "Client values:"
echo "  Provider:       $PROVIDER"
echo "  Room ID:        $ACTUAL_ROOM_ID"
echo "  Encryption key: $KEY"
echo "  Transport:      $TRANSPORT_TYPE"
echo ""