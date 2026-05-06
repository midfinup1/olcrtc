// Package main provides the BareBoneVPN CLI entrypoint.
package main

import (
	"context"
	"flag"
	"fmt"
	"os"
	"os/signal"
	"path/filepath"
	"strings"
	"syscall"
	"time"

	"github.com/openlibrecommunity/olcrtc/internal/app/session"
	"github.com/openlibrecommunity/olcrtc/internal/bootstrap"
	"github.com/openlibrecommunity/olcrtc/internal/logger"
)

type config struct {
	mode      string
	link      string
	transport string
	carrier   string
	roomID    string
	provider  string

	socksPort int
	socksHost string

	keyHex string
	debug  bool

	dataDir   string
	dnsServer string

	socksProxyAddr string
	socksProxyPort int

	bootstrapAction string
	clientID        string
	bootstrapToken  string

	bootstrapClientsFile     string
	bootstrapPersonalDataDir string
	bootstrapRoomPrefix      string
}

func main() {
	if err := run(); err != nil {
		logger.Error(err)
		os.Exit(1)
	}
}

func run() error {
	session.RegisterDefaults()

	cfg := parseFlags()
	configureLogging(cfg.debug)

	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()

	sigCh := make(chan os.Signal, 1)
	signal.Notify(sigCh, os.Interrupt, syscall.SIGTERM)

	switch cfg.mode {
	case "bootstrap-cnc":
		errCh := make(chan error, 1)

		go func() {
			errCh <- runBootstrapClient(ctx, cfg)
		}()

		select {
		case <-sigCh:
			logger.Info("Shutting down gracefully...")
			cancel()
			return waitForShutdown(errCh)

		case err := <-errCh:
			return err
		}

	case "bootstrap-srv":
		errCh := make(chan error, 1)

		go func() {
			errCh <- runBootstrapServer(ctx, cfg)
		}()

		select {
		case <-sigCh:
			logger.Info("Shutting down gracefully...")
			cancel()
			return waitForShutdown(errCh)

		case err := <-errCh:
			return err
		}
	}

	sessionCfg := toSessionConfig(cfg)
	if err := session.Validate(sessionCfg); err != nil {
		return err
	}

	errCh := make(chan error, 1)

	go func() {
		errCh <- session.Run(ctx, sessionCfg)
	}()

	select {
	case <-sigCh:
		logger.Info("Shutting down gracefully...")
		cancel()
		return waitForShutdown(errCh)

	case err := <-errCh:
		return err
	}
}

func parseFlags() config {
	cfg := config{}

	flag.StringVar(&cfg.mode, "mode", "", "Mode: srv, cnc, bootstrap-srv or bootstrap-cnc")
	flag.StringVar(&cfg.link, "link", session.DefaultLink, "Link: direct")
	flag.StringVar(&cfg.transport, "transport", session.DefaultTransport, "Transport: datachannel")
	flag.StringVar(&cfg.carrier, "carrier", "", "Carrier: jazz, wbstream, telemost")
	flag.StringVar(&cfg.provider, "provider", "", "Deprecated alias for -carrier")
	flag.StringVar(&cfg.roomID, "id", "", "Room ID")
	flag.StringVar(&cfg.keyHex, "key", "", "Shared encryption key as 64 hex characters")

	flag.StringVar(&cfg.socksHost, "socks-host", session.DefaultSOCKSHost, "SOCKS5 listen host (client only)")
	flag.IntVar(&cfg.socksPort, "socks-port", session.DefaultSOCKSPort, "SOCKS5 listen port (client only)")

	flag.StringVar(&cfg.dataDir, "data", session.DefaultDataDir, "Path to data directory")
	flag.StringVar(&cfg.dnsServer, "dns", session.DefaultDNSServer, "DNS server (for example 1.1.1.1:53)")

	flag.StringVar(&cfg.socksProxyAddr, "socks-proxy", "", "SOCKS5 proxy address for server egress")
	flag.IntVar(&cfg.socksProxyPort, "socks-proxy-port", 0, "SOCKS5 proxy port for server egress")

	flag.StringVar(&cfg.bootstrapAction, "bootstrap-action", "", "Bootstrap client action: register or rotate")
	flag.StringVar(&cfg.clientID, "client-id", "", "Client ID for bootstrap mode")
	flag.StringVar(&cfg.bootstrapToken, "bootstrap-token", "", "Bootstrap token")

	flag.StringVar(&cfg.bootstrapClientsFile, "bootstrap-clients-file", "", "Bootstrap server clients JSON file")
	flag.StringVar(&cfg.bootstrapPersonalDataDir, "bootstrap-personal-data", "", "Bootstrap server personal clients data directory")
	flag.StringVar(&cfg.bootstrapRoomPrefix, "bootstrap-room-prefix", bootstrap.DefaultRoomPrefix, "Bootstrap server personal room prefix")

	flag.BoolVar(&cfg.debug, "debug", false, "Enable verbose logging")

	flag.Parse()

	return cfg
}

func configureLogging(debug bool) {
	if debug {
		logger.SetVerbose(true)
	}
}

func runBootstrapClient(ctx context.Context, cfg config) error {
	carrier := firstNonEmpty(cfg.carrier, cfg.provider)

	if strings.TrimSpace(carrier) == "" {
		return fmt.Errorf("bootstrap carrier/provider required")
	}

	if strings.TrimSpace(cfg.roomID) == "" {
		return fmt.Errorf("bootstrap room id required")
	}

	if strings.TrimSpace(cfg.keyHex) == "" {
		return fmt.Errorf("bootstrap key required")
	}

	if strings.TrimSpace(cfg.bootstrapAction) == "" {
		return fmt.Errorf("bootstrap action required: use -bootstrap-action register or -bootstrap-action rotate")
	}

	if strings.TrimSpace(cfg.clientID) == "" {
		return fmt.Errorf("client id required: use -client-id")
	}

	if strings.TrimSpace(cfg.bootstrapToken) == "" {
		return fmt.Errorf("bootstrap token required: use -bootstrap-token")
	}

	dataDir, err := resolveDataDir(cfg.dataDir)
	if err != nil {
		return err
	}

	return bootstrap.RunClient(ctx, bootstrap.Config{
		LinkName:       cfg.link,
		TransportName:  cfg.transport,
		CarrierName:    carrier,
		BootstrapRoom:  cfg.roomID,
		BootstrapKey:   cfg.keyHex,
		DNSServer:      cfg.dnsServer,
		DataDir:        dataDir,
		ClientID:        cfg.clientID,
		BootstrapToken: cfg.bootstrapToken,
		Action:          cfg.bootstrapAction,
		Timeout:         45 * time.Second,
	})
}

func runBootstrapServer(ctx context.Context, cfg config) error {
	carrier := firstNonEmpty(cfg.carrier, cfg.provider)

	if strings.TrimSpace(carrier) == "" {
		return fmt.Errorf("bootstrap server carrier/provider required")
	}

	if strings.TrimSpace(cfg.roomID) == "" {
		return fmt.Errorf("bootstrap server room id required")
	}

	if strings.TrimSpace(cfg.keyHex) == "" {
		return fmt.Errorf("bootstrap server key required")
	}

	if strings.TrimSpace(cfg.bootstrapToken) == "" {
		return fmt.Errorf("bootstrap server token required: use -bootstrap-token")
	}

	dataDir, err := resolveDataDir(cfg.dataDir)
	if err != nil {
		return err
	}

	clientsFile := strings.TrimSpace(cfg.bootstrapClientsFile)
	if clientsFile == "" {
		clientsFile = filepath.Join(dataDir, "bootstrap", "clients.json")
	}

	if !filepath.IsAbs(clientsFile) {
		clientsFile = filepath.Join(dataDir, clientsFile)
	}

	personalDataDir := strings.TrimSpace(cfg.bootstrapPersonalDataDir)
	if personalDataDir == "" {
		personalDataDir = filepath.Join(dataDir, "bootstrap", "personal")
	}

	if !filepath.IsAbs(personalDataDir) {
		personalDataDir = filepath.Join(dataDir, personalDataDir)
	}

	binaryPath, err := os.Executable()
	if err != nil {
		return fmt.Errorf("resolve executable path failed: %w", err)
	}

	return bootstrap.RunServer(ctx, bootstrap.ServerConfig{
		LinkName:       cfg.link,
		TransportName:  cfg.transport,
		CarrierName:    carrier,
		BootstrapRoom:  cfg.roomID,
		BootstrapKey:   cfg.keyHex,
		BootstrapToken: cfg.bootstrapToken,
		DNSServer:      cfg.dnsServer,

		ClientsFile:     clientsFile,
		PersonalDataDir: personalDataDir,
		RoomPrefix:      cfg.bootstrapRoomPrefix,
		BinaryPath:      binaryPath,

		PersonalLinkName:      cfg.link,
		PersonalTransportName: cfg.transport,
		PersonalCarrierName:   carrier,
	})
}

func resolveDataDir(dataDir string) (string, error) {
	if dataDir == "" {
		return "", fmt.Errorf("data directory required (use -data data)")
	}

	if filepath.IsAbs(dataDir) {
		return dataDir, nil
	}

	exePath, err := os.Executable()
	if err != nil {
		return "", fmt.Errorf("resolve executable path: %w", err)
	}

	return filepath.Join(filepath.Dir(exePath), dataDir), nil
}

func toSessionConfig(cfg config) session.Config {
	return session.Config{
		Mode:           cfg.mode,
		Link:           cfg.link,
		Transport:      cfg.transport,
		Carrier:        firstNonEmpty(cfg.carrier, cfg.provider),
		RoomID:         cfg.roomID,
		KeyHex:         cfg.keyHex,
		SOCKSHost:      cfg.socksHost,
		SOCKSPort:      cfg.socksPort,
		DNSServer:      cfg.dnsServer,
		SOCKSProxyAddr: cfg.socksProxyAddr,
		SOCKSProxyPort: cfg.socksProxyPort,
	}
}

func firstNonEmpty(values ...string) string {
	for _, value := range values {
		if value != "" {
			return value
		}
	}

	return ""
}

func waitForShutdown(errCh <-chan error) error {
	done := make(chan error, 1)

	go func() {
		done <- <-errCh
	}()

	select {
	case err := <-done:
		if err == nil {
			logger.Info("Shutdown complete")
		}
		return err

	case <-time.After(5 * time.Second):
		logger.Warn("Shutdown timeout, forcing exit")
		return nil
	}
}