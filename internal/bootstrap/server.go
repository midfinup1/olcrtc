package bootstrap

import (
	"bufio"
	"context"
	"crypto/rand"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
	"os"
	"os/exec"
	"path/filepath"
	"regexp"
	"strings"
	"sync"
	"time"

	"github.com/openlibrecommunity/olcrtc/internal/link"
	"github.com/openlibrecommunity/olcrtc/internal/logger"
	"github.com/openlibrecommunity/olcrtc/internal/names"
)

type ServerConfig struct {
	LinkName       string
	TransportName  string
	CarrierName    string
	BootstrapRoom  string
	BootstrapKey   string
	BootstrapToken string
	DNSServer       string

	ClientsFile     string
	PersonalDataDir string
	RoomPrefix      string
	BinaryPath      string

	PersonalLinkName      string
	PersonalTransportName string
	PersonalCarrierName   string
}

type ClientRecord struct {
	ClientID      string `json:"client_id"`
	RoomID        string `json:"room_id"`
	EncryptionKey string `json:"encryption_key"`
	Provider      string `json:"provider"`
	Transport     string `json:"transport"`
	DNSServer      string `json:"dns_server"`
	Enabled        bool   `json:"enabled"`
	CreatedAt      string `json:"created_at"`
	UpdatedAt      string `json:"updated_at"`
}

type ClientStoreFile struct {
	Clients map[string]ClientRecord `json:"clients"`
}

type PersonalProcess struct {
	ClientID string
	Cmd      *exec.Cmd
	LogFile  *os.File
	Cancel   context.CancelFunc
}

type Server struct {
	cfg ServerConfig

	cipher *cryptoCipherWrapper

	mu        sync.Mutex
	store     ClientStoreFile
	processes map[string]*PersonalProcess
}

type cryptoCipherWrapper struct {
	encrypt func([]byte) ([]byte, error)
	decrypt func([]byte) ([]byte, error)
}

func RunServer(ctx context.Context, cfg ServerConfig) error {
	if err := validateServerConfig(cfg); err != nil {
		return err
	}

	cipher, err := setupCipher(cfg.BootstrapKey)
	if err != nil {
		return fmt.Errorf("bootstrap server setup cipher failed: %w", err)
	}

	server := &Server{
		cfg: cfg,
		cipher: &cryptoCipherWrapper{
			encrypt: cipher.Encrypt,
			decrypt: cipher.Decrypt,
		},
		processes: make(map[string]*PersonalProcess),
		store: ClientStoreFile{
			Clients: make(map[string]ClientRecord),
		},
	}

	if err := server.loadStore(); err != nil {
		return err
	}

	if err := server.ensureKnownClientsRunning(ctx); err != nil {
		return err
	}

	defer server.stopAllPersonalProcesses()

	return server.runBootstrapLoop(ctx)
}

func validateServerConfig(cfg ServerConfig) error {
	if strings.TrimSpace(cfg.LinkName) == "" {
		return errors.New("bootstrap server link is required")
	}

	if strings.TrimSpace(cfg.TransportName) == "" {
		return errors.New("bootstrap server transport is required")
	}

	if strings.TrimSpace(cfg.CarrierName) == "" {
		return errors.New("bootstrap server carrier/provider is required")
	}

	if strings.TrimSpace(cfg.BootstrapRoom) == "" {
		return errors.New("bootstrap server room id is required")
	}

	if strings.TrimSpace(cfg.BootstrapKey) == "" {
		return errors.New("bootstrap server key is required")
	}

	if strings.TrimSpace(cfg.BootstrapToken) == "" {
		return errors.New("bootstrap server token is required")
	}

	if strings.TrimSpace(cfg.ClientsFile) == "" {
		return errors.New("bootstrap server clients file is required")
	}

	if strings.TrimSpace(cfg.PersonalDataDir) == "" {
		return errors.New("bootstrap server personal data dir is required")
	}

	if strings.TrimSpace(cfg.BinaryPath) == "" {
		return errors.New("bootstrap server binary path is required")
	}

	if strings.TrimSpace(cfg.PersonalLinkName) == "" {
		return errors.New("bootstrap server personal link is required")
	}

	if strings.TrimSpace(cfg.PersonalTransportName) == "" {
		return errors.New("bootstrap server personal transport is required")
	}

	if strings.TrimSpace(cfg.PersonalCarrierName) == "" {
		return errors.New("bootstrap server personal carrier/provider is required")
	}

	return nil
}

func (s *Server) loadStore() error {
	s.mu.Lock()
	defer s.mu.Unlock()

	dir := filepath.Dir(s.cfg.ClientsFile)
	if err := os.MkdirAll(dir, 0o700); err != nil {
		return fmt.Errorf("create clients dir failed: %w", err)
	}

	if _, err := os.Stat(s.cfg.ClientsFile); os.IsNotExist(err) {
		s.store = ClientStoreFile{
			Clients: make(map[string]ClientRecord),
		}
		return s.saveStoreLocked()
	}

	raw, err := os.ReadFile(s.cfg.ClientsFile)
	if err != nil {
		return fmt.Errorf("read clients file failed: %w", err)
	}

	if len(strings.TrimSpace(string(raw))) == 0 {
		s.store = ClientStoreFile{
			Clients: make(map[string]ClientRecord),
		}
		return s.saveStoreLocked()
	}

	if err := json.Unmarshal(raw, &s.store); err != nil {
		return fmt.Errorf("parse clients file failed: %w", err)
	}

	if s.store.Clients == nil {
		s.store.Clients = make(map[string]ClientRecord)
	}

	return nil
}

func (s *Server) saveStoreLocked() error {
	dir := filepath.Dir(s.cfg.ClientsFile)
	if err := os.MkdirAll(dir, 0o700); err != nil {
		return fmt.Errorf("create clients dir failed: %w", err)
	}

	raw, err := json.MarshalIndent(s.store, "", "  ")
	if err != nil {
		return fmt.Errorf("marshal clients file failed: %w", err)
	}

	tmp := s.cfg.ClientsFile + ".tmp"

	if err := os.WriteFile(tmp, raw, 0o600); err != nil {
		return fmt.Errorf("write clients tmp file failed: %w", err)
	}

	if err := os.Rename(tmp, s.cfg.ClientsFile); err != nil {
		return fmt.Errorf("replace clients file failed: %w", err)
	}

	return nil
}

func (s *Server) ensureKnownClientsRunning(ctx context.Context) error {
	s.mu.Lock()
	records := make([]ClientRecord, 0, len(s.store.Clients))

	for _, record := range s.store.Clients {
		if record.Enabled {
			records = append(records, record)
		}
	}

	s.mu.Unlock()

	for _, record := range records {
		if err := s.ensurePersonalProcess(ctx, record); err != nil {
			logger.Warnf("failed to start personal room for client=%s: %v", record.ClientID, err)
		}
	}

	return nil
}

func (s *Server) runBootstrapLoop(ctx context.Context) error {
	for {
		select {
		case <-ctx.Done():
			return nil

		default:
		}

		err := s.runOneBootstrapLink(ctx)

		if ctx.Err() != nil {
			return nil
		}

		if err != nil {
			logger.Warnf("bootstrap link stopped: %v", err)
		}

		time.Sleep(2 * time.Second)
	}
}

func (s *Server) runOneBootstrapLink(ctx context.Context) error {
	linkDone := make(chan string, 1)

	var ln link.Link

	onData := func(data []byte) {
		if ln == nil {
			return
		}

		go func() {
			if err := s.handleBootstrapData(ctx, ln, data); err != nil {
				logger.Warnf("bootstrap request handling error: %v", err)
			}
		}()
	}

	created, err := link.New(ctx, s.cfg.LinkName, link.Config{
		Transport: s.cfg.TransportName,
		Carrier:   s.cfg.CarrierName,
		RoomURL:   s.cfg.BootstrapRoom,
		Name:      names.Generate(),
		OnData:    onData,
		DNSServer: s.cfg.DNSServer,
	})
	if err != nil {
		return fmt.Errorf("create bootstrap link failed: %w", err)
	}

	ln = created

	ln.SetEndedCallback(func(reason string) {
		select {
		case linkDone <- reason:
		default:
		}
	})

	logger.Infof("bootstrap server connecting room=%s carrier=%s transport=%s", s.cfg.BootstrapRoom, s.cfg.CarrierName, s.cfg.TransportName)

	if err := ln.Connect(ctx); err != nil {
		_ = ln.Close()
		return fmt.Errorf("connect bootstrap link failed: %w", err)
	}

	go ln.WatchConnection(ctx)

	logger.Infof("bootstrap server ready room=%s", s.cfg.BootstrapRoom)

	select {
	case <-ctx.Done():
		_ = ln.Close()
		return nil

	case reason := <-linkDone:
		_ = ln.Close()
		return fmt.Errorf("bootstrap room ended: %s", reason)
	}
}

func (s *Server) handleBootstrapData(ctx context.Context, ln link.Link, data []byte) error {
	plaintext, err := s.cipher.decrypt(data)
	if err != nil {
		return fmt.Errorf("bootstrap decrypt failed: %w", err)
	}

	var request Request
	if err := json.Unmarshal(plaintext, &request); err != nil {
		return s.sendError(ctx, ln, "invalid request json")
	}

	if strings.TrimSpace(request.Token) != s.cfg.BootstrapToken {
		logger.Warnf("bootstrap rejected invalid token client_id=%s", request.ClientID)
		return s.sendError(ctx, ln, "invalid token")
	}

	clientID := strings.TrimSpace(request.ClientID)
	if clientID == "" {
		return s.sendError(ctx, ln, "client_id is empty")
	}

	if !isSafeClientID(clientID) {
		return s.sendError(ctx, ln, "client_id contains invalid characters")
	}

	switch request.Type {
	case MessageRegister:
		record, err := s.getOrCreateClient(ctx, clientID)
		if err != nil {
			return s.sendError(ctx, ln, err.Error())
		}

		if err := s.ensurePersonalProcess(ctx, record); err != nil {
			return s.sendError(ctx, ln, err.Error())
		}

		return s.sendConfig(ctx, ln, record)

	case MessageRotateRoom:
		record, err := s.rotateClient(ctx, clientID)
		if err != nil {
			return s.sendError(ctx, ln, err.Error())
		}

		if err := s.ensurePersonalProcess(ctx, record); err != nil {
			return s.sendError(ctx, ln, err.Error())
		}

		return s.sendConfig(ctx, ln, record)

	default:
		return s.sendError(ctx, ln, "unknown bootstrap request type")
	}
}

func (s *Server) getOrCreateClient(ctx context.Context, clientID string) (ClientRecord, error) {
	s.mu.Lock()

	if record, ok := s.store.Clients[clientID]; ok {
		if !record.Enabled {
			record.Enabled = true
			record.UpdatedAt = time.Now().UTC().Format(time.RFC3339Nano)
			s.store.Clients[clientID] = record

			if err := s.saveStoreLocked(); err != nil {
				s.mu.Unlock()
				return ClientRecord{}, err
			}
		}

		s.mu.Unlock()
		return record, nil
	}

	now := time.Now().UTC().Format(time.RFC3339Nano)

	keyHex, err := generateHexKey32()
	if err != nil {
		s.mu.Unlock()
		return ClientRecord{}, err
	}

	record := ClientRecord{
		ClientID:      clientID,
		RoomID:        "any",
		EncryptionKey: keyHex,
		Provider:      s.cfg.PersonalCarrierName,
		Transport:     s.cfg.PersonalTransportName,
		DNSServer:      s.cfg.DNSServer,
		Enabled:        true,
		CreatedAt:      now,
		UpdatedAt:      now,
	}

	s.mu.Unlock()

	realRoomID, err := s.startTemporaryAnyRoomAndGetID(ctx, record)
	if err != nil {
		return ClientRecord{}, err
	}

	record.RoomID = realRoomID
	record.UpdatedAt = time.Now().UTC().Format(time.RFC3339Nano)

	s.mu.Lock()
	s.store.Clients[clientID] = record

	if err := s.saveStoreLocked(); err != nil {
		s.mu.Unlock()
		return ClientRecord{}, err
	}

	s.mu.Unlock()

	logger.Infof("created client config client_id=%s room_id=%s", record.ClientID, record.RoomID)

	return record, nil
}

func (s *Server) rotateClient(ctx context.Context, clientID string) (ClientRecord, error) {
	s.stopPersonalProcess(clientID)

	s.mu.Lock()

	now := time.Now().UTC().Format(time.RFC3339Nano)

	record, ok := s.store.Clients[clientID]
	if !ok {
		record = ClientRecord{
			ClientID:  clientID,
			Provider:  s.cfg.PersonalCarrierName,
			Transport: s.cfg.PersonalTransportName,
			DNSServer: s.cfg.DNSServer,
			Enabled:   true,
			CreatedAt: now,
		}
	}

	keyHex, err := generateHexKey32()
	if err != nil {
		s.mu.Unlock()
		return ClientRecord{}, err
	}

	record.EncryptionKey = keyHex
	record.RoomID = "any"
	record.Provider = s.cfg.PersonalCarrierName
	record.Transport = s.cfg.PersonalTransportName
	record.DNSServer = s.cfg.DNSServer
	record.Enabled = true
	record.UpdatedAt = now

	s.mu.Unlock()

	realRoomID, err := s.startTemporaryAnyRoomAndGetID(ctx, record)
	if err != nil {
		return ClientRecord{}, err
	}

	record.RoomID = realRoomID
	record.UpdatedAt = time.Now().UTC().Format(time.RFC3339Nano)

	s.mu.Lock()
	s.store.Clients[clientID] = record

	if err := s.saveStoreLocked(); err != nil {
		s.mu.Unlock()
		return ClientRecord{}, err
	}

	s.mu.Unlock()

	logger.Infof("rotated client config client_id=%s room_id=%s", record.ClientID, record.RoomID)

	return record, nil
}

func (s *Server) startTemporaryAnyRoomAndGetID(ctx context.Context, record ClientRecord) (string, error) {
	clientDataDir := filepath.Join(s.cfg.PersonalDataDir, record.ClientID, "data-create")
	clientLogDir := filepath.Join(s.cfg.PersonalDataDir, record.ClientID, "logs")

	if err := os.MkdirAll(clientDataDir, 0o700); err != nil {
		return "", fmt.Errorf("create temporary data dir failed: %w", err)
	}

	if err := os.MkdirAll(clientLogDir, 0o700); err != nil {
		return "", fmt.Errorf("create temporary log dir failed: %w", err)
	}

	logPath := filepath.Join(clientLogDir, "create-room.log")

	_ = os.Remove(logPath)

	logFile, err := os.OpenFile(logPath, os.O_CREATE|os.O_APPEND|os.O_WRONLY, 0o600)
	if err != nil {
		return "", fmt.Errorf("open temporary room log failed: %w", err)
	}

	processCtx, cancel := context.WithCancel(ctx)

	args := []string{
		"-mode", "srv",
		"-link", s.cfg.PersonalLinkName,
		"-transport", record.Transport,
		"-provider", record.Provider,
		"-id", "any",
		"-key", record.EncryptionKey,
		"-data", clientDataDir,
		"-dns", record.DNSServer,
		"-debug",
	}

	cmd := exec.CommandContext(processCtx, s.cfg.BinaryPath, args...)
	cmd.Stdout = logFile
	cmd.Stderr = logFile

	if err := cmd.Start(); err != nil {
		cancel()
		_ = logFile.Close()
		return "", fmt.Errorf("start temporary WB room creator failed client_id=%s: %w", record.ClientID, err)
	}

	roomID, waitErr := waitRoomIDFromLog(ctx, logPath, 25*time.Second)

	cancel()

	if cmd.Process != nil {
		_ = cmd.Process.Kill()
	}

	_ = cmd.Wait()
	_ = logFile.Close()

	if waitErr != nil {
		raw, _ := os.ReadFile(logPath)
		return "", fmt.Errorf("%w\ncreate-room.log:\n%s", waitErr, string(raw))
	}

	if strings.TrimSpace(roomID) == "" {
		return "", errors.New("created WB room id is empty")
	}

	logger.Infof("created WB room via any client_id=%s room_id=%s", record.ClientID, roomID)

	return roomID, nil
}

func (s *Server) ensurePersonalProcess(ctx context.Context, record ClientRecord) error {
	if strings.TrimSpace(record.ClientID) == "" {
		return errors.New("cannot start personal process: client_id is empty")
	}

	if strings.TrimSpace(record.RoomID) == "" {
		return errors.New("cannot start personal process: room_id is empty")
	}

	if strings.TrimSpace(record.EncryptionKey) == "" {
		return errors.New("cannot start personal process: encryption_key is empty")
	}

	s.mu.Lock()
	existing := s.processes[record.ClientID]
	s.mu.Unlock()

	if existing != nil && existing.Cmd != nil && existing.Cmd.Process != nil && existing.Cmd.ProcessState == nil {
		return nil
	}

	return s.startPersonalProcess(ctx, record)
}

func (s *Server) startPersonalProcess(ctx context.Context, record ClientRecord) error {
	clientDataDir := filepath.Join(s.cfg.PersonalDataDir, record.ClientID, "data")
	clientLogDir := filepath.Join(s.cfg.PersonalDataDir, record.ClientID, "logs")

	if err := os.MkdirAll(clientDataDir, 0o700); err != nil {
		return fmt.Errorf("create personal data dir failed: %w", err)
	}

	if err := os.MkdirAll(clientLogDir, 0o700); err != nil {
		return fmt.Errorf("create personal log dir failed: %w", err)
	}

	logPath := filepath.Join(clientLogDir, "server.log")

	logFile, err := os.OpenFile(logPath, os.O_CREATE|os.O_APPEND|os.O_WRONLY, 0o600)
	if err != nil {
		return fmt.Errorf("open personal log failed: %w", err)
	}

	processCtx, cancel := context.WithCancel(ctx)

	args := []string{
		"-mode", "srv",
		"-link", s.cfg.PersonalLinkName,
		"-transport", record.Transport,
		"-provider", record.Provider,
		"-id", record.RoomID,
		"-key", record.EncryptionKey,
		"-data", clientDataDir,
		"-dns", record.DNSServer,
		"-debug",
	}

	cmd := exec.CommandContext(processCtx, s.cfg.BinaryPath, args...)
	cmd.Stdout = logFile
	cmd.Stderr = logFile

	if err := cmd.Start(); err != nil {
		cancel()
		_ = logFile.Close()
		return fmt.Errorf("start personal server failed client_id=%s: %w", record.ClientID, err)
	}

	process := &PersonalProcess{
		ClientID: record.ClientID,
		Cmd:      cmd,
		LogFile:  logFile,
		Cancel:   cancel,
	}

	s.mu.Lock()
	s.processes[record.ClientID] = process
	s.mu.Unlock()

	logger.Infof("started personal server client_id=%s room_id=%s pid=%d", record.ClientID, record.RoomID, cmd.Process.Pid)

	go s.watchPersonalProcess(ctx, record)

	return nil
}

func (s *Server) watchPersonalProcess(ctx context.Context, record ClientRecord) {
	s.mu.Lock()
	process := s.processes[record.ClientID]
	s.mu.Unlock()

	if process == nil || process.Cmd == nil {
		return
	}

	err := process.Cmd.Wait()

	if process.LogFile != nil {
		_ = process.LogFile.Close()
	}

	s.mu.Lock()
	current := s.processes[record.ClientID]
	if current == process {
		delete(s.processes, record.ClientID)
	}
	s.mu.Unlock()

	if ctx.Err() != nil {
		return
	}

	logger.Warnf("personal server exited client_id=%s room_id=%s err=%v", record.ClientID, record.RoomID, err)

	time.Sleep(2 * time.Second)

	s.mu.Lock()
	stored, ok := s.store.Clients[record.ClientID]
	s.mu.Unlock()

	if !ok || !stored.Enabled {
		return
	}

	if err := s.ensurePersonalProcess(ctx, stored); err != nil {
		logger.Warnf("personal server restart failed client_id=%s: %v", record.ClientID, err)
	}
}

func (s *Server) stopPersonalProcess(clientID string) {
	s.mu.Lock()
	process := s.processes[clientID]
	if process != nil {
		delete(s.processes, clientID)
	}
	s.mu.Unlock()

	if process == nil {
		return
	}

	if process.Cancel != nil {
		process.Cancel()
	}

	if process.Cmd != nil && process.Cmd.Process != nil && process.Cmd.ProcessState == nil {
		_ = process.Cmd.Process.Kill()
	}

	if process.LogFile != nil {
		_ = process.LogFile.Close()
	}
}

func (s *Server) stopAllPersonalProcesses() {
	s.mu.Lock()
	clientIDs := make([]string, 0, len(s.processes))

	for clientID := range s.processes {
		clientIDs = append(clientIDs, clientID)
	}

	s.mu.Unlock()

	for _, clientID := range clientIDs {
		s.stopPersonalProcess(clientID)
	}
}

func (s *Server) sendConfig(ctx context.Context, ln link.Link, record ClientRecord) error {
	response := Response{
		Type:          MessageConfig,
		ClientID:      record.ClientID,
		Provider:      record.Provider,
		RoomID:        record.RoomID,
		EncryptionKey: record.EncryptionKey,
		Transport:     record.Transport,
		DNSServer:     record.DNSServer,
	}

	return s.sendResponse(ctx, ln, response)
}

func (s *Server) sendError(ctx context.Context, ln link.Link, message string) error {
	response := Response{
		Type:    MessageError,
		Message: message,
	}

	return s.sendResponse(ctx, ln, response)
}

func (s *Server) sendResponse(ctx context.Context, ln link.Link, response Response) error {
	raw, err := json.Marshal(response)
	if err != nil {
		return fmt.Errorf("marshal bootstrap response failed: %w", err)
	}

	encrypted, err := s.cipher.encrypt(raw)
	if err != nil {
		return fmt.Errorf("encrypt bootstrap response failed: %w", err)
	}

	if err := waitCanSend(ctx, ln); err != nil {
		return err
	}

	if err := ln.Send(encrypted); err != nil {
		return fmt.Errorf("send bootstrap response failed: %w", err)
	}

	logger.Infof("bootstrap response sent type=%s client_id=%s", response.Type, response.ClientID)

	return nil
}

func generateHexKey32() (string, error) {
	buf := make([]byte, 32)

	if _, err := rand.Read(buf); err != nil {
		return "", err
	}

	return hex.EncodeToString(buf), nil
}

func randomHex(size int) string {
	buf := make([]byte, size)

	if _, err := rand.Read(buf); err != nil {
		return fmt.Sprintf("%d", time.Now().UnixNano())
	}

	return hex.EncodeToString(buf)
}

var safeClientIDRegexp = regexp.MustCompile(`^[a-zA-Z0-9._-]+$`)

func isSafeClientID(clientID string) bool {
	if len(clientID) < 3 {
		return false
	}

	if len(clientID) > 80 {
		return false
	}

	return safeClientIDRegexp.MatchString(clientID)
}

var unsafeClientIDRegexp = regexp.MustCompile(`[^a-zA-Z0-9._-]+`)

func sanitizeClientID(clientID string) string {
	value := strings.TrimSpace(clientID)
	value = unsafeClientIDRegexp.ReplaceAllString(value, "-")
	value = strings.Trim(value, "-._")

	if value == "" {
		return "client"
	}

	if len(value) > 48 {
		return value[:48]
	}

	return value
}

var wbRoomIDRegexp = regexp.MustCompile(`[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}`)

func extractRoomIDFromText(text string) string {
	matches := wbRoomIDRegexp.FindAllString(text, -1)
	if len(matches) == 0 {
		return ""
	}

	return strings.ToLower(matches[len(matches)-1])
}

func waitRoomIDFromLog(ctx context.Context, logPath string, timeout time.Duration) (string, error) {
	deadline := time.NewTimer(timeout)
	defer deadline.Stop()

	ticker := time.NewTicker(250 * time.Millisecond)
	defer ticker.Stop()

	var position int64

	for {
		select {
		case <-ctx.Done():
			return "", ctx.Err()

		case <-deadline.C:
			return "", fmt.Errorf("timeout waiting for WB room id in log: %s", logPath)

		case <-ticker.C:
			file, err := os.Open(logPath)
			if err != nil {
				continue
			}

			if position > 0 {
				_, _ = file.Seek(position, 0)
			}

			scanner := bufio.NewScanner(file)
			scanner.Buffer(make([]byte, 1024), 1024*1024)

			for scanner.Scan() {
				line := scanner.Text()

				if roomID := extractRoomIDFromText(line); roomID != "" {
					_ = file.Close()
					return roomID, nil
				}
			}

			if current, err := file.Seek(0, 1); err == nil {
				position = current
			}

			_ = file.Close()
		}
	}
}