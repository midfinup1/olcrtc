// Package bootstrap implements short-lived client-side bootstrap exchange.
//
// Bootstrap mode is used before normal SOCKS tunnel connection:
//
//   1. Client connects to a permanent bootstrap room.
//   2. Client sends REGISTER or ROTATE_ROOM request.
//   3. Server responds with personal room config.
//   4. Client prints BB_CONFIG_JSON=... to stdout and exits.
//
// This package intentionally does not start SOCKS5 and does not use mux.
// It only performs one encrypted JSON exchange over the WebRTC data channel.
package bootstrap

import (
	"context"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
	"strings"
	"time"

	"github.com/openlibrecommunity/olcrtc/internal/crypto"
	"github.com/openlibrecommunity/olcrtc/internal/link"
	"github.com/openlibrecommunity/olcrtc/internal/logger"
	"github.com/openlibrecommunity/olcrtc/internal/names"
)

const (
	ActionRegister = "register"
	ActionRotate   = "rotate"

	MessageRegister   = "REGISTER"
	MessageRotateRoom = "ROTATE_ROOM"
	MessageConfig     = "CONFIG"
	MessageError      = "ERROR"

	DefaultTimeout = 45 * time.Second
)

var (
	ErrInvalidBootstrapAction = errors.New("invalid bootstrap action")
	ErrBootstrapTimeout       = errors.New("bootstrap timeout")
	ErrBootstrapServerError   = errors.New("bootstrap server error")
	ErrInvalidBootstrapConfig = errors.New("invalid bootstrap config")
)

type Request struct {
	Type     string `json:"type"`
	ClientID string `json:"client_id"`
	Token    string `json:"token"`
}

type Response struct {
	Type string `json:"type"`

	ClientID      string `json:"client_id,omitempty"`
	Provider      string `json:"provider,omitempty"`
	RoomID        string `json:"room_id,omitempty"`
	EncryptionKey string `json:"encryption_key,omitempty"`
	Transport     string `json:"transport,omitempty"`
	DNSServer     string `json:"dns_server,omitempty"`

	Message string `json:"message,omitempty"`
}

type Config struct {
	LinkName       string
	TransportName  string
	CarrierName    string
	BootstrapRoom  string
	BootstrapKey   string
	DNSServer       string
	DataDir         string
	ClientID        string
	BootstrapToken string
	Action          string
	Timeout         time.Duration
}

func RunClient(ctx context.Context, cfg Config) error {
	if err := validateConfig(cfg); err != nil {
		return err
	}

	timeout := cfg.Timeout
	if timeout <= 0 {
		timeout = DefaultTimeout
	}

	runCtx, cancel := context.WithTimeout(ctx, timeout)
	defer cancel()

	cipher, err := setupCipher(cfg.BootstrapKey)
	if err != nil {
		return fmt.Errorf("bootstrap setup cipher failed: %w", err)
	}

	responseCh := make(chan Response, 1)
	errorCh := make(chan error, 1)

	onData := func(data []byte) {
		plaintext, err := cipher.Decrypt(data)
		if err != nil {
			select {
			case errorCh <- fmt.Errorf("bootstrap decrypt failed: %w", err):
			default:
			}
			return
		}

		var response Response
		if err := json.Unmarshal(plaintext, &response); err != nil {
			select {
			case errorCh <- fmt.Errorf("bootstrap response JSON parse failed: %w; body=%s", err, string(plaintext)):
			default:
			}
			return
		}

		select {
		case responseCh <- response:
		default:
		}
	}

	ln, err := link.New(runCtx, cfg.LinkName, link.Config{
		Transport: cfg.TransportName,
		Carrier:   cfg.CarrierName,
		RoomURL:   cfg.BootstrapRoom,
		Name:      names.Generate(),
		OnData:    onData,
		DNSServer: cfg.DNSServer,
	})
	if err != nil {
		return fmt.Errorf("bootstrap create link failed: %w", err)
	}
	defer func() {
		_ = ln.Close()
	}()

	ln.SetEndedCallback(func(reason string) {
		select {
		case errorCh <- fmt.Errorf("bootstrap room ended: %s", reason):
		default:
		}
	})

	logger.Infof("bootstrap connecting to room=%s carrier=%s transport=%s", cfg.BootstrapRoom, cfg.CarrierName, cfg.TransportName)

	if err := ln.Connect(runCtx); err != nil {
		return fmt.Errorf("bootstrap connect failed: %w", err)
	}

	go ln.WatchConnection(runCtx)

	if err := waitCanSend(runCtx, ln); err != nil {
		return err
	}

	request := Request{
		Type:     requestTypeFromAction(cfg.Action),
		ClientID: cfg.ClientID,
		Token:    cfg.BootstrapToken,
	}

	rawRequest, err := json.Marshal(request)
	if err != nil {
		return fmt.Errorf("bootstrap request marshal failed: %w", err)
	}

	encryptedRequest, err := cipher.Encrypt(rawRequest)
	if err != nil {
		return fmt.Errorf("bootstrap request encrypt failed: %w", err)
	}

	logger.Infof("bootstrap sending action=%s client_id=%s", cfg.Action, cfg.ClientID)

	if err := ln.Send(encryptedRequest); err != nil {
		return fmt.Errorf("bootstrap request send failed: %w", err)
	}

	for {
		select {
		case <-runCtx.Done():
			return ErrBootstrapTimeout

		case err := <-errorCh:
			return err

		case response := <-responseCh:
			if response.Type == MessageError {
				if strings.TrimSpace(response.Message) == "" {
					return ErrBootstrapServerError
				}
				return fmt.Errorf("%w: %s", ErrBootstrapServerError, response.Message)
			}

			if response.Type != MessageConfig {
				logger.Warnf("bootstrap ignored response type=%s", response.Type)
				continue
			}

			if err := validateResponse(response); err != nil {
				return err
			}

			out, err := json.Marshal(response)
			if err != nil {
				return fmt.Errorf("bootstrap config marshal failed: %w", err)
			}

			fmt.Printf("BB_CONFIG_JSON=%s\n", string(out))
			return nil
		}
	}
}

func validateConfig(cfg Config) error {
	if strings.TrimSpace(cfg.LinkName) == "" {
		return errors.New("bootstrap link is required")
	}

	if strings.TrimSpace(cfg.TransportName) == "" {
		return errors.New("bootstrap transport is required")
	}

	if strings.TrimSpace(cfg.CarrierName) == "" {
		return errors.New("bootstrap carrier/provider is required")
	}

	if strings.TrimSpace(cfg.BootstrapRoom) == "" {
		return errors.New("bootstrap room id is required")
	}

	if strings.TrimSpace(cfg.BootstrapKey) == "" {
		return errors.New("bootstrap key is required")
	}

	if strings.TrimSpace(cfg.ClientID) == "" {
		return errors.New("client id is required")
	}

	if strings.TrimSpace(cfg.BootstrapToken) == "" {
		return errors.New("bootstrap token is required")
	}

	action := strings.TrimSpace(strings.ToLower(cfg.Action))
	if action != ActionRegister && action != ActionRotate {
		return fmt.Errorf("%w: %s", ErrInvalidBootstrapAction, cfg.Action)
	}

	return nil
}

func validateResponse(response Response) error {
	if strings.TrimSpace(response.Provider) == "" {
		return fmt.Errorf("%w: provider is empty", ErrInvalidBootstrapConfig)
	}

	if strings.TrimSpace(response.RoomID) == "" {
		return fmt.Errorf("%w: room_id is empty", ErrInvalidBootstrapConfig)
	}

	if strings.TrimSpace(response.EncryptionKey) == "" {
		return fmt.Errorf("%w: encryption_key is empty", ErrInvalidBootstrapConfig)
	}

	if strings.TrimSpace(response.Transport) == "" {
		return fmt.Errorf("%w: transport is empty", ErrInvalidBootstrapConfig)
	}

	if strings.TrimSpace(response.DNSServer) == "" {
		return fmt.Errorf("%w: dns_server is empty", ErrInvalidBootstrapConfig)
	}

	key, err := hex.DecodeString(response.EncryptionKey)
	if err != nil {
		return fmt.Errorf("%w: encryption_key is not hex: %v", ErrInvalidBootstrapConfig, err)
	}

	if len(key) != 32 {
		return fmt.Errorf("%w: encryption_key must be 32 bytes, got %d", ErrInvalidBootstrapConfig, len(key))
	}

	return nil
}

func requestTypeFromAction(action string) string {
	switch strings.TrimSpace(strings.ToLower(action)) {
	case ActionRotate:
		return MessageRotateRoom
	default:
		return MessageRegister
	}
}

func setupCipher(keyHex string) (*crypto.Cipher, error) {
	key, err := hex.DecodeString(strings.TrimSpace(keyHex))
	if err != nil {
		return nil, fmt.Errorf("failed to decode key: %w", err)
	}

	if len(key) != 32 {
		return nil, fmt.Errorf("key must be 32 bytes, got %d", len(key))
	}

	cipher, err := crypto.NewCipher(string(key))
	if err != nil {
		return nil, fmt.Errorf("failed to create cipher: %w", err)
	}

	return cipher, nil
}

func waitCanSend(ctx context.Context, ln link.Link) error {
	ticker := time.NewTicker(100 * time.Millisecond)
	defer ticker.Stop()

	timeout := time.NewTimer(20 * time.Second)
	defer timeout.Stop()

	for {
		if ln.CanSend() {
			return nil
		}

		select {
		case <-ctx.Done():
			return ctx.Err()

		case <-timeout.C:
			return errors.New("bootstrap data channel is not ready")

		case <-ticker.C:
		}
	}
}