package wbchat

import (
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"net/http"
	"net/url"
	"os"
	"strconv"
	"strings"
	"sync/atomic"
	"time"

	"github.com/gorilla/websocket"
	"github.com/openlibrecommunity/olcrtc/internal/protect"
)

const (
	apiBase = "https://stream.wb.ru"
	wsURL   = "wss://stream.wb.ru/api-chat/connection/websocket"
)

type Client struct {
	accessToken string
	cookie      string
	httpClient  *http.Client
	nextID      atomic.Int64
}

func NewClient(accessToken string) *Client {
	c := &Client{
		accessToken: strings.TrimSpace(accessToken),
		cookie:      strings.TrimSpace(os.Getenv("WB_COOKIE")),
		httpClient:  protect.NewHTTPClient(),
	}

	c.nextID.Store(0)

	return c
}

func (c *Client) EnsureAccessToken(ctx context.Context, displayName string) error {
	if strings.TrimSpace(c.accessToken) != "" {
		return nil
	}

	token, err := RegisterGuest(ctx, displayName)
	if err != nil {
		return err
	}

	c.accessToken = token

	return nil
}

func RegisterGuest(ctx context.Context, displayName string) (string, error) {
	displayName = strings.TrimSpace(displayName)

	if displayName == "" {
		displayName = "BareBoneVPN"
	}

	u := apiBase + "/auth/api/v1/auth/user/guest-register"

	reqBody := guestRegisterRequest{
		DisplayName: displayName,
		Device: device{
			DeviceName: "Linux",
			DeviceType: "PARTICIPANT_DEVICE_TYPE_WEB_DESKTOP",
		},
	}

	body, err := json.Marshal(reqBody)
	if err != nil {
		return "", fmt.Errorf("marshal guest request: %w", err)
	}

	req, err := http.NewRequestWithContext(ctx, http.MethodPost, u, bytes.NewReader(body))
	if err != nil {
		return "", fmt.Errorf("create guest request: %w", err)
	}

	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("User-Agent", "Mozilla/5.0 (Linux x86_64)")

	client := protect.NewHTTPClient()

	resp, err := client.Do(req)
	if err != nil {
		return "", fmt.Errorf("do guest request: %w", err)
	}

	defer func() {
		_ = resp.Body.Close()
	}()

	if resp.StatusCode != http.StatusOK {
		raw, _ := io.ReadAll(resp.Body)
		return "", fmt.Errorf("guest register failed: %d %s", resp.StatusCode, raw)
	}

	var result guestRegisterResponse

	if err := json.NewDecoder(resp.Body).Decode(&result); err != nil {
		return "", fmt.Errorf("decode guest response: %w", err)
	}

	result.AccessToken = strings.TrimSpace(result.AccessToken)

	if result.AccessToken == "" {
		return "", errors.New("guest access token is empty")
	}

	return result.AccessToken, nil
}

func (c *Client) nextCommandID() int64 {
	return c.nextID.Add(1)
}

func (c *Client) GetConnectionToken(ctx context.Context, roomID string) (string, error) {
	roomID = strings.TrimSpace(roomID)

	if roomID == "" {
		return "", errors.New("room id is empty")
	}

	u := apiBase + "/api-chat/api/v1/connection-token"

	req, err := http.NewRequestWithContext(ctx, http.MethodGet, u, nil)
	if err != nil {
		return "", fmt.Errorf("create request: %w", err)
	}

	c.setHTTPHeaders(req, roomID)

	resp, err := c.httpClient.Do(req)
	if err != nil {
		return "", fmt.Errorf("do request: %w", err)
	}

	defer func() {
		_ = resp.Body.Close()
	}()

	if resp.StatusCode != http.StatusOK {
		body, _ := io.ReadAll(resp.Body)
		return "", fmt.Errorf("get connection token failed: %d %s", resp.StatusCode, body)
	}

	var result connectionTokenResponse

	if err := json.NewDecoder(resp.Body).Decode(&result); err != nil {
		return "", fmt.Errorf("decode response: %w", err)
	}

	result.ConnectionToken = strings.TrimSpace(result.ConnectionToken)

	if result.ConnectionToken == "" {
		return "", errors.New("connection token is empty")
	}

	return result.ConnectionToken, nil
}

func (c *Client) GetChat(ctx context.Context, roomID string, displayName string) (ChatInfo, error) {
	roomID = strings.TrimSpace(roomID)
	displayName = strings.TrimSpace(displayName)

	if roomID == "" {
		return ChatInfo{}, errors.New("room id is empty")
	}

	if displayName == "" {
		displayName = "BareBoneVPN"
	}

	u := fmt.Sprintf("%s/api-chat/api/v1/chat/%s", apiBase, url.PathEscape(roomID))

	req, err := http.NewRequestWithContext(ctx, http.MethodGet, u, nil)
	if err != nil {
		return ChatInfo{}, fmt.Errorf("create request: %w", err)
	}

	q := req.URL.Query()
	q.Set("displayName", displayName)
	req.URL.RawQuery = q.Encode()

	c.setHTTPHeaders(req, roomID)

	resp, err := c.httpClient.Do(req)
	if err != nil {
		return ChatInfo{}, fmt.Errorf("do request: %w", err)
	}

	defer func() {
		_ = resp.Body.Close()
	}()

	if resp.StatusCode != http.StatusOK {
		body, _ := io.ReadAll(resp.Body)
		return ChatInfo{}, fmt.Errorf("get chat failed: %d %s", resp.StatusCode, body)
	}

	var result ChatInfo

	if err := json.NewDecoder(resp.Body).Decode(&result); err != nil {
		return ChatInfo{}, fmt.Errorf("decode response: %w", err)
	}

	if result.ChatID == 0 {
		return ChatInfo{}, errors.New("chat id is empty")
	}

	if strings.TrimSpace(result.ChatToken) == "" {
		return ChatInfo{}, errors.New("chat token is empty")
	}

	return result, nil
}

func (c *Client) GetMessages(ctx context.Context, roomID string, chatID int64, limit int) ([]ChatMessage, error) {
	roomID = strings.TrimSpace(roomID)

	if roomID == "" {
		return nil, errors.New("room id is empty")
	}

	if chatID == 0 {
		return nil, errors.New("chat id is empty")
	}

	if limit <= 0 {
		limit = 50
	}

	u := fmt.Sprintf("%s/api-chat/api/v1/chat/%d/messages", apiBase, chatID)

	req, err := http.NewRequestWithContext(ctx, http.MethodGet, u, nil)
	if err != nil {
		return nil, fmt.Errorf("create request: %w", err)
	}

	q := req.URL.Query()
	q.Set("limit", strconv.Itoa(limit))
	req.URL.RawQuery = q.Encode()

	c.setHTTPHeaders(req, roomID)

	resp, err := c.httpClient.Do(req)
	if err != nil {
		return nil, fmt.Errorf("do request: %w", err)
	}

	defer func() {
		_ = resp.Body.Close()
	}()

	if resp.StatusCode != http.StatusOK {
		body, _ := io.ReadAll(resp.Body)
		return nil, fmt.Errorf("get messages failed: %d %s", resp.StatusCode, body)
	}

	raw, err := io.ReadAll(resp.Body)
	if err != nil {
		return nil, fmt.Errorf("read response: %w", err)
	}

	var direct []ChatMessage
	if err := json.Unmarshal(raw, &direct); err == nil {
		return direct, nil
	}

	var wrapped MessagesResponse
	if err := json.Unmarshal(raw, &wrapped); err == nil {
		return wrapped.Messages, nil
	}

	return nil, fmt.Errorf("decode messages failed: %s", raw)
}

func (c *Client) ConnectWebSocket(ctx context.Context, roomID string) (*websocket.Conn, error) {
	roomID = strings.TrimSpace(roomID)

	if roomID == "" {
		return nil, errors.New("room id is empty")
	}

	connectionToken, err := c.GetConnectionToken(ctx, roomID)
	if err != nil {
		return nil, fmt.Errorf("get connection token failed: %w", err)
	}

	headers := http.Header{}
	headers.Set("Origin", "https://stream.wb.ru")
	headers.Set("User-Agent", "Mozilla/5.0 (Linux x86_64)")
	headers.Set("Referer", "https://stream.wb.ru/room/"+roomID)

	if c.cookie != "" {
		headers.Set("Cookie", c.cookie)
	}

	if c.accessToken != "" {
		headers.Set("Authorization", "Bearer "+c.accessToken)
	}

	dialer := websocket.Dialer{
		HandshakeTimeout: 15 * time.Second,
		Proxy:            http.ProxyFromEnvironment,
	}

	conn, resp, err := dialer.DialContext(ctx, wsURL, headers)
	if err != nil {
		if resp != nil && resp.Body != nil {
			body, _ := io.ReadAll(resp.Body)
			_ = resp.Body.Close()
			return nil, fmt.Errorf("connect websocket failed: %w: %d %s", err, resp.StatusCode, body)
		}

		return nil, fmt.Errorf("connect websocket failed: %w", err)
	}

	if err := c.connectCentrifugoWS(ctx, conn, connectionToken); err != nil {
		_ = conn.Close()
		return nil, fmt.Errorf("connect centrifugo failed: %w", err)
	}

	return conn, nil
}

func (c *Client) connectCentrifugoWS(ctx context.Context, conn *websocket.Conn, connectionToken string) error {
	connectionToken = strings.TrimSpace(connectionToken)

	if connectionToken == "" {
		return errors.New("connection token is empty")
	}

	id := c.nextCommandID()

	frame := map[string]any{
		"id": id,
		"connect": map[string]any{
			"token": connectionToken,
			"name":  "js",
		},
	}

	if err := c.writeJSON(ctx, conn, frame); err != nil {
		return err
	}

	return c.waitCommandAck(ctx, conn, id)
}

func (c *Client) SubscribeChatWS(ctx context.Context, conn *websocket.Conn, chatID int64, chatToken string) error {
	if chatID == 0 {
		return errors.New("chat id is empty")
	}

	chatToken = strings.TrimSpace(chatToken)
	if chatToken == "" {
		return errors.New("chat token is empty")
	}

	id := c.nextCommandID()

	frame := map[string]any{
		"id": id,
		"subscribe": map[string]any{
			"channel": fmt.Sprintf("chat:%d", chatID),
			"token":   chatToken,
		},
	}

	if err := c.writeJSON(ctx, conn, frame); err != nil {
		return err
	}

	return c.waitCommandAck(ctx, conn, id)
}

func (c *Client) SendTextWS(ctx context.Context, conn *websocket.Conn, chatID int64, text string) error {
	if chatID == 0 {
		return errors.New("chat id is empty")
	}

	text = strings.TrimSpace(text)
	if text == "" {
		return errors.New("text is empty")
	}

	id := c.nextCommandID()

	frame := wsFrame{
		ID: id,
		Publish: &wsPublish{
			Channel: fmt.Sprintf("chat:%d", chatID),
			Data: sendMessageData{
				Type: "sendMessageRequest",
				Payload: sendMessagePayload{
					TextPayload: textPayload{
						Text: text,
					},
				},
			},
		},
	}

	if err := c.writeJSON(ctx, conn, frame); err != nil {
		return fmt.Errorf("write websocket message failed: %w", err)
	}

	return nil
}

func (c *Client) ReadLoop(ctx context.Context, conn *websocket.Conn, onText func(ChatMessage), onRaw func([]byte)) error {
	if conn == nil {
		return errors.New("websocket is nil")
	}

	for {
		select {
		case <-ctx.Done():
			return nil

		default:
		}

		_ = conn.SetReadDeadline(time.Now().Add(30 * time.Second))

		_, raw, err := conn.ReadMessage()
		if err != nil {
			if ctx.Err() != nil {
				return nil
			}

			return fmt.Errorf("read websocket message failed: %w", err)
		}

		if onRaw != nil {
			onRaw(raw)
		}

		var frame wsFrame
		if err := json.Unmarshal(raw, &frame); err != nil {
			continue
		}

		if frame.Push == nil {
			continue
		}

		if frame.Push.Pub.Data.Type != "messageCreated" {
			continue
		}

		msg, err := parseMessageCreated(frame.Push.Pub.Data.Payload)
		if err != nil {
			continue
		}

		if onText != nil {
			onText(msg)
		}
	}
}

func (c *Client) waitCommandAck(ctx context.Context, conn *websocket.Conn, commandID int64) error {
	deadline := time.Now().Add(10 * time.Second)

	if ctxDeadline, ok := ctx.Deadline(); ok && ctxDeadline.Before(deadline) {
		deadline = ctxDeadline
	}

	for {
		select {
		case <-ctx.Done():
			return ctx.Err()

		default:
		}

		_ = conn.SetReadDeadline(deadline)

		_, raw, err := conn.ReadMessage()
		if err != nil {
			return fmt.Errorf("read command ack failed: %w", err)
		}

		var frame map[string]any
		if err := json.Unmarshal(raw, &frame); err != nil {
			continue
		}

		idValue, ok := frame["id"]
		if !ok {
			continue
		}

		idFloat, ok := idValue.(float64)
		if !ok {
			continue
		}

		if int64(idFloat) != commandID {
			continue
		}

		if errValue, ok := frame["error"]; ok && errValue != nil {
			errRaw, _ := json.Marshal(errValue)
			return fmt.Errorf("command id=%d failed: %s", commandID, errRaw)
		}

		return nil
	}
}

func (c *Client) writeJSON(ctx context.Context, conn *websocket.Conn, value any) error {
	if conn == nil {
		return errors.New("websocket is nil")
	}

	if deadline, ok := ctx.Deadline(); ok {
		_ = conn.SetWriteDeadline(deadline)
	} else {
		_ = conn.SetWriteDeadline(time.Now().Add(15 * time.Second))
	}

	if err := conn.WriteJSON(value); err != nil {
		return fmt.Errorf("write websocket json failed: %w", err)
	}

	return nil
}

func parseMessageCreated(payload map[string]any) (ChatMessage, error) {
	raw, err := json.Marshal(payload)
	if err != nil {
		return ChatMessage{}, err
	}

	var msg ChatMessage

	if err := json.Unmarshal(raw, &msg); err != nil {
		return ChatMessage{}, err
	}

	if msg.ID == 0 {
		return ChatMessage{}, errors.New("message id is empty")
	}

	return msg, nil
}

func (c *Client) setHTTPHeaders(req *http.Request, roomID string) {
	req.Header.Set("Accept", "*/*")
	req.Header.Set("User-Agent", "Mozilla/5.0 (Linux x86_64)")
	req.Header.Set("Origin", "https://stream.wb.ru")
	req.Header.Set("Referer", "https://stream.wb.ru/room/"+roomID)

	if c.cookie != "" {
		req.Header.Set("Cookie", c.cookie)
	}

	if c.accessToken != "" {
		req.Header.Set("Authorization", "Bearer "+c.accessToken)
	}
}