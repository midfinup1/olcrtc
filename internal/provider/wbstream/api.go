package wbstream

import (
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"net/http"
	"strings"

	"github.com/openlibrecommunity/olcrtc/internal/protect"
)

const apiBase = "https://stream.wb.ru"

var (
	errGuestRegister = errors.New("guest register failed")
	errCreateRoom    = errors.New("create room failed")
	errJoinRoom      = errors.New("join room failed")
	errGetToken      = errors.New("get token failed")
)

type guestRegisterRequest struct {
	DisplayName string `json:"displayName"`
	Device      device `json:"device"`
}

type device struct {
	DeviceName string `json:"deviceName"`
	DeviceType string `json:"deviceType"`
}

type guestRegisterResponse struct {
	AccessToken string `json:"accessToken"`
}

type createRoomRequest struct {
	RoomID      string `json:"roomId,omitempty"`
	RoomType    string `json:"roomType"`
	RoomPrivacy string `json:"roomPrivacy"`
}

type createRoomResponse struct {
	RoomID string `json:"roomId"`
}

type tokenResponse struct {
	RoomToken       string `json:"roomToken"`
	ConnectionToken string `json:"connectionToken"`
}

type connectionDetailsResponse struct {
	RoomToken string `json:"roomToken"`
	ServerURL string `json:"serverUrl"`
	RTCConfig struct {
		ICEServers []struct {
			URLs       []string `json:"urls"`
			Username   string   `json:"username"`
			Credential string   `json:"credential"`
		} `json:"iceServers"`
	} `json:"rtcConfig"`
}

func registerGuest(ctx context.Context, displayName string) (string, error) {
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
		return "", fmt.Errorf("marshal request body: %w", err)
	}

	req, err := http.NewRequestWithContext(ctx, http.MethodPost, u, bytes.NewBuffer(body))
	if err != nil {
		return "", fmt.Errorf("create request: %w", err)
	}

	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("User-Agent", "Mozilla/5.0 (Linux x86_64)")

	client := protect.NewHTTPClient()

	resp, err := client.Do(req)
	if err != nil {
		return "", fmt.Errorf("do request: %w", err)
	}

	defer func() {
		_ = resp.Body.Close()
	}()

	if resp.StatusCode != http.StatusOK {
		b, _ := io.ReadAll(resp.Body)
		return "", fmt.Errorf("%w: %d %s", errGuestRegister, resp.StatusCode, b)
	}

	var res guestRegisterResponse

	if err := json.NewDecoder(resp.Body).Decode(&res); err != nil {
		return "", fmt.Errorf("decode response: %w", err)
	}

	if strings.TrimSpace(res.AccessToken) == "" {
		return "", errors.New("guest access token is empty")
	}

	return res.AccessToken, nil
}

func createRoom(ctx context.Context, accessToken string, requestedRoomID ...string) (string, error) {
	u := apiBase + "/api-room/api/v2/room"

	roomID := ""

	if len(requestedRoomID) > 0 {
		roomID = strings.TrimSpace(requestedRoomID[0])
	}

	if roomID == "any" {
		roomID = ""
	}

	reqBody := createRoomRequest{
		RoomID:      roomID,
		RoomType:    "ROOM_TYPE_ALL_ON_SCREEN",
		RoomPrivacy: "ROOM_PRIVACY_FREE",
	}

	body, err := json.Marshal(reqBody)
	if err != nil {
		return "", fmt.Errorf("marshal request body: %w", err)
	}

	req, err := http.NewRequestWithContext(ctx, http.MethodPost, u, bytes.NewBuffer(body))
	if err != nil {
		return "", fmt.Errorf("create request: %w", err)
	}

	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("Authorization", "Bearer "+accessToken)
	req.Header.Set("User-Agent", "Mozilla/5.0 (Linux x86_64)")

	client := protect.NewHTTPClient()

	resp, err := client.Do(req)
	if err != nil {
		return "", fmt.Errorf("do request: %w", err)
	}

	defer func() {
		_ = resp.Body.Close()
	}()

	if resp.StatusCode != http.StatusOK && resp.StatusCode != http.StatusCreated {
		b, _ := io.ReadAll(resp.Body)
		return "", fmt.Errorf("%w: %d %s", errCreateRoom, resp.StatusCode, b)
	}

	var res createRoomResponse

	if err := json.NewDecoder(resp.Body).Decode(&res); err != nil {
		return "", fmt.Errorf("decode response: %w", err)
	}

	res.RoomID = strings.TrimSpace(res.RoomID)

	if res.RoomID == "" {
		return "", errors.New("created room id is empty")
	}

	if roomID != "" && res.RoomID != roomID {
		return "", fmt.Errorf("provider returned different room_id: want=%s got=%s", roomID, res.RoomID)
	}

	return res.RoomID, nil
}

func joinRoom(ctx context.Context, accessToken, roomID string) error {
	roomID = strings.TrimSpace(roomID)

	if roomID == "" {
		return errors.New("room id is empty")
	}

	u := fmt.Sprintf("%s/api-room/api/v1/room/%s/join", apiBase, roomID)

	req, err := http.NewRequestWithContext(ctx, http.MethodPost, u, bytes.NewReader([]byte("{}")))
	if err != nil {
		return fmt.Errorf("create request: %w", err)
	}

	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("Authorization", "Bearer "+accessToken)
	req.Header.Set("User-Agent", "Mozilla/5.0 (Linux x86_64)")
	req.Header.Set("Origin", "https://stream.wb.ru")
	req.Header.Set("Referer", "https://stream.wb.ru/room/"+roomID)

	client := protect.NewHTTPClient()

	resp, err := client.Do(req)
	if err != nil {
		return fmt.Errorf("do request: %w", err)
	}

	defer func() {
		_ = resp.Body.Close()
	}()

	if resp.StatusCode != http.StatusOK {
		b, _ := io.ReadAll(resp.Body)
		return fmt.Errorf("%w: %d %s", errJoinRoom, resp.StatusCode, b)
	}

	return nil
}

func getConnectionDetails(ctx context.Context, accessToken, roomID, displayName string) (string, string, error) {
	roomID = strings.TrimSpace(roomID)
	displayName = strings.TrimSpace(displayName)

	if roomID == "" {
		return "", "", errors.New("room id is empty")
	}

	if displayName == "" {
		displayName = "Linux"
	}

	u := fmt.Sprintf("%s/api-room-manager/v2/room/%s/connection-details", apiBase, roomID)

	req, err := http.NewRequestWithContext(ctx, http.MethodGet, u, nil)
	if err != nil {
		return "", "", fmt.Errorf("create request: %w", err)
	}

	q := req.URL.Query()
	q.Add("deviceType", "PARTICIPANT_DEVICE_TYPE_WEB_DESKTOP")
	q.Add("displayName", displayName)
	req.URL.RawQuery = q.Encode()

	req.Header.Set("Authorization", "Bearer "+accessToken)
	req.Header.Set("User-Agent", "Mozilla/5.0 (Linux x86_64)")
	req.Header.Set("Accept", "*/*")
	req.Header.Set("Referer", "https://stream.wb.ru/room/"+roomID)

	client := protect.NewHTTPClient()

	resp, err := client.Do(req)
	if err != nil {
		return "", "", fmt.Errorf("do request: %w", err)
	}

	defer func() {
		_ = resp.Body.Close()
	}()

	if resp.StatusCode != http.StatusOK {
		b, _ := io.ReadAll(resp.Body)
		return "", "", fmt.Errorf("%w: %d %s", errGetToken, resp.StatusCode, b)
	}

	var res connectionDetailsResponse

	if err := json.NewDecoder(resp.Body).Decode(&res); err != nil {
		return "", "", fmt.Errorf("decode response: %w", err)
	}

	roomToken := strings.TrimSpace(res.RoomToken)
	serverURL := strings.TrimSpace(res.ServerURL)

	if roomToken == "" {
		return "", "", errors.New("room token is empty")
	}

	if serverURL == "" {
		return "", "", errors.New("server url is empty")
	}

	return roomToken, serverURL, nil
}

func getToken(ctx context.Context, accessToken, roomID, displayName string) (string, error) {
	token, _, err := getConnectionDetails(ctx, accessToken, roomID, displayName)
	if err == nil {
		return token, nil
	}

	roomID = strings.TrimSpace(roomID)

	if roomID == "" {
		return "", errors.New("room id is empty")
	}

	u := fmt.Sprintf("%s/api-room-manager/api/v1/room/%s/token", apiBase, roomID)

	req, reqErr := http.NewRequestWithContext(ctx, http.MethodGet, u, nil)
	if reqErr != nil {
		return "", fmt.Errorf("create request: %w", reqErr)
	}

	q := req.URL.Query()
	q.Add("deviceType", "PARTICIPANT_DEVICE_TYPE_WEB_DESKTOP")
	q.Add("displayName", displayName)
	req.URL.RawQuery = q.Encode()

	req.Header.Set("Authorization", "Bearer "+accessToken)
	req.Header.Set("User-Agent", "Mozilla/5.0 (Linux x86_64)")
	req.Header.Set("Accept", "*/*")

	client := protect.NewHTTPClient()

	resp, reqErr := client.Do(req)
	if reqErr != nil {
		return "", fmt.Errorf("do request: %w", reqErr)
	}

	defer func() {
		_ = resp.Body.Close()
	}()

	if resp.StatusCode != http.StatusOK {
		b, _ := io.ReadAll(resp.Body)
		return "", fmt.Errorf("%w: connection-details failed: %v; legacy token failed: %d %s", errGetToken, err, resp.StatusCode, b)
	}

	var res tokenResponse

	if reqErr := json.NewDecoder(resp.Body).Decode(&res); reqErr != nil {
		return "", fmt.Errorf("decode response: %w", reqErr)
	}

	legacyToken := strings.TrimSpace(res.RoomToken)
	if legacyToken == "" {
		legacyToken = strings.TrimSpace(res.ConnectionToken)
	}

	if legacyToken == "" {
		return "", errors.New("room token is empty")
	}

	return legacyToken, nil
}

func isWBRoomNotFoundError(err error) bool {
	if err == nil {
		return false
	}

	text := err.Error()

	return strings.Contains(text, "join room failed: 404") ||
		strings.Contains(text, "404") && strings.Contains(text, "not found") ||
		strings.Contains(text, `"code":5`) ||
		strings.Contains(text, `"message":"not found"`)
}

func isWBRateLimitError(err error) bool {
	if err == nil {
		return false
	}

	text := strings.ToLower(err.Error())

	return strings.Contains(text, "429") ||
		strings.Contains(text, "too many requests")
}