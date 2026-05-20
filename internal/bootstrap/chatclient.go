package bootstrap

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"log"
	"strings"
	"time"
)

type ClientConfig struct {

	BootstrapRoom  string
	BootstrapKey   string
	BootstrapToken string
	ClientID        string
	RotateRoom     bool

}

func RunChatClient(ctx context.Context, cfg ClientConfig) (Response, error) {
	if strings.TrimSpace(cfg.BootstrapRoom) == "" {
		return Response{}, errors.New("bootstrap room is empty")
	}

	if strings.TrimSpace(cfg.BootstrapKey) == "" {
		return Response{}, errors.New("bootstrap key is empty")
	}

	if strings.TrimSpace(cfg.BootstrapToken) == "" {
		return Response{}, errors.New("bootstrap token is empty")
	}

	if strings.TrimSpace(cfg.ClientID) == "" {
		return Response{}, errors.New("client_id is empty")
	}

	cipher, err := setupCipher(cfg.BootstrapKey)
	if err != nil {
		return Response{}, fmt.Errorf("setup bootstrap cipher failed: %w", err)
	}

	action := MessageRegister
	if cfg.RotateRoom {
		action = MessageRotateRoom
	}

	request := Request{
		Type:     action,
		ClientID: cfg.ClientID,
		Token:    cfg.BootstrapToken,
	}

	rawRequest, err := json.Marshal(request)
	if err != nil {
		return Response{}, fmt.Errorf("marshal bootstrap request failed: %w", err)
	}

	encryptedRequest, err := cipher.Encrypt(rawRequest)
	if err != nil {
		return Response{}, fmt.Errorf("encrypt bootstrap request failed: %w", err)
	}

	displayName := "BareBone Client " + cfg.ClientID

	transport := NewChatBootstrapTransport("", cfg.BootstrapRoom, displayName)

	connectCtx, cancelConnect := context.WithTimeout(ctx, 30*time.Second)
	defer cancelConnect()

	if err := transport.Connect(connectCtx); err != nil {
		return Response{}, fmt.Errorf("connect chat bootstrap failed: %w", err)
	}

	defer func() {
		_ = transport.Close()
	}()

	transport.StartKeepAlive(ctx)

	log.Printf("chat bootstrap connected room=%s", cfg.BootstrapRoom)

	waitCtx, cancelWait := context.WithTimeout(ctx, 60*time.Second)
	defer cancelWait()

	responseCh := make(chan Response, 1)
	errCh := make(chan error, 1)

	go func() {
		err := transport.ReadEncryptedLoop(waitCtx, func(encrypted []byte) {
			plaintext, err := cipher.Decrypt(encrypted)
			if err != nil {
				return
			}

			var response Response
			if err := json.Unmarshal(plaintext, &response); err != nil {
				return
			}

			if response.ClientID != "" && response.ClientID != cfg.ClientID {
				return
			}

			if response.Type != MessageConfig && response.Type != MessageError {
				return
			}

			select {
			case responseCh <- response:
			default:
			}
		})

		if err != nil {
			select {
			case errCh <- err:
			default:
			}
		}
	}()

	time.Sleep(500 * time.Millisecond)

	log.Printf("chat bootstrap sending action=%s client_id=%s", action, cfg.ClientID)

	if err := transport.SendEncrypted(waitCtx, encryptedRequest); err != nil {
		return Response{}, fmt.Errorf("send chat bootstrap request failed: %w", err)
	}

	select {
	case <-waitCtx.Done():
		return Response{}, fmt.Errorf("chat bootstrap timeout: %w", waitCtx.Err())

	case err := <-errCh:
		return Response{}, err

	case response := <-responseCh:
		if response.Type == MessageError {
			return Response{}, fmt.Errorf("bootstrap error: %s", response.Message)
		}

		if response.Type != MessageConfig {
			return Response{}, fmt.Errorf("unexpected bootstrap response type: %s", response.Type)
		}

		if response.ClientID != cfg.ClientID {
			return Response{}, fmt.Errorf("bootstrap response client_id mismatch: want=%s got=%s", cfg.ClientID, response.ClientID)
		}

		log.Printf("chat bootstrap received config client_id=%s room=%s provider=%s transport=%s", response.ClientID, response.RoomID, response.Provider, response.Transport)

		return response, nil
	}
}