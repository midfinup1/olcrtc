package bootstrap

import (
	"context"
	"encoding/base64"
	"errors"
	"fmt"
	"log"
	"strings"
	"time"

	"github.com/gorilla/websocket"
	"github.com/openlibrecommunity/olcrtc/internal/bootstrap/wbchat"
)

const chatBootstrapPrefix = "BBVPN1:"

type ChatBootstrapTransport struct {
	roomID      string
	displayName string
	accessToken string

	chatClient *wbchat.Client
	chatInfo   wbchat.ChatInfo
	conn       *websocket.Conn
}

func NewChatBootstrapTransport(accessToken string, roomID string, displayName string) *ChatBootstrapTransport {
	return &ChatBootstrapTransport{
		roomID:      strings.TrimSpace(roomID),
		displayName: strings.TrimSpace(displayName),
		accessToken: strings.TrimSpace(accessToken),
	}
}

func (t *ChatBootstrapTransport) Connect(ctx context.Context) error {
	if t.roomID == "" {
		return errors.New("chat bootstrap room id is empty")
	}

	if t.displayName == "" {
		t.displayName = "BareBoneVPN"
	}

	t.chatClient = wbchat.NewClient(t.accessToken)

	if err := t.chatClient.EnsureAccessToken(ctx, t.displayName); err != nil {
		return fmt.Errorf("ensure chat access token failed: %w", err)
	}

	chatInfo, err := t.chatClient.GetChat(ctx, t.roomID, t.displayName)
	if err != nil {
		return fmt.Errorf("get chat failed: %w", err)
	}

	conn, err := t.chatClient.ConnectWebSocket(ctx, t.roomID)
	if err != nil {
		return fmt.Errorf("connect chat websocket failed: %w", err)
	}

	if err := t.chatClient.SubscribeChatWS(ctx, conn, chatInfo.ChatID, chatInfo.ChatToken); err != nil {
		_ = conn.Close()
		return fmt.Errorf("subscribe chat failed: %w", err)
	}

	t.chatInfo = chatInfo
	t.conn = conn

	log.Printf("WB Chat bootstrap connected room=%s chat_id=%d", t.roomID, t.chatInfo.ChatID)

	return nil
}

func (t *ChatBootstrapTransport) Close() error {
	if t.conn != nil {
		return t.conn.Close()
	}

	return nil
}

func (t *ChatBootstrapTransport) SendEncrypted(ctx context.Context, encrypted []byte) error {
	if t.chatClient == nil || t.conn == nil {
		return errors.New("chat bootstrap transport is not connected")
	}

	text := chatBootstrapPrefix + base64.StdEncoding.EncodeToString(encrypted)

	if err := t.chatClient.SendTextWS(ctx, t.conn, t.chatInfo.ChatID, text); err != nil {
		return fmt.Errorf("send chat bootstrap message failed: %w", err)
	}

	return nil
}

func (t *ChatBootstrapTransport) ReadEncryptedLoop(ctx context.Context, onMessage func([]byte)) error {
	if t.chatClient == nil || t.conn == nil {
		return errors.New("chat bootstrap transport is not connected")
	}

	return t.chatClient.ReadLoop(ctx, t.conn, func(msg wbchat.ChatMessage) {
		text := strings.TrimSpace(msg.Text)

		if !strings.HasPrefix(text, chatBootstrapPrefix) {
			return
		}

		encoded := strings.TrimPrefix(text, chatBootstrapPrefix)

		encrypted, err := base64.StdEncoding.DecodeString(encoded)
		if err != nil {
			log.Printf("WB Chat bootstrap decode failed message_id=%d: %v", msg.ID, err)
			return
		}

		onMessage(encrypted)
	}, nil)
}

func (t *ChatBootstrapTransport) StartKeepAlive(ctx context.Context) {
	go func() {
		ticker := time.NewTicker(20 * time.Second)
		defer ticker.Stop()

		for {
			select {
			case <-ctx.Done():
				return

			case <-ticker.C:
				if t.conn == nil {
					continue
				}

				_ = t.conn.WriteMessage(websocket.TextMessage, []byte("{}"))
			}
		}
	}()
}