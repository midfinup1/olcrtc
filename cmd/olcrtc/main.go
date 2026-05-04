// Package main provides the olcrtc CLI entrypoint.
package main

import (
	"context"
	"flag"
	"fmt"
	"os"
	"os/signal"
	"path/filepath"
	"syscall"
	"time"

	"github.com/openlibrecommunity/olcrtc/internal/app/session"
	"github.com/openlibrecommunity/olcrtc/internal/logger"
)

type config struct {
	mode           string
	link           string
	transport      string
	carrier        string
	roomID         string
	provider       string
	socksPort      int
	socksHost      string
	keyHex         string
	debug          bool
	dataDir        string
	dnsServer      string
	socksProxyAddr string
	socksProxyPort int
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

	sessionCfg := toSessionConfig(cfg)
	if err := session.Validate(sessionCfg); err != nil {
		return err
	}

	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()

	sigCh := make(chan os.Signal, 1)
	signal.Notify(sigCh, os.Interrupt, syscall.SIGTERM)

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

	flag.StringVar(&cfg.mode, "mode", "", "Mode: srv or cnc")
	flag.StringVar(&cfg.link, "link", session.DefaultLink, "Link: direct")
	flag.StringVar(&cfg.transport, "transport", session.DefaultTransport, "Transport: datachannel")
	flag.StringVar(&cfg.carrier, "carrier", "", "Carrier: jazz or wbstream")
	flag.StringVar(&cfg.provider, "provider", "", "Deprecated alias for -carrier")
	flag.StringVar(&cfg.roomID, "id", "", "Room ID")
	flag.StringVar(&cfg.keyHex, "key", "", "Shared encryption key as 64 hex characters")
	flag.StringVar(&cfg.socksHost, "socks-host", session.DefaultSOCKSHost, "SOCKS5 listen host (client only)")
	flag.IntVar(&cfg.socksPort, "socks-port", session.DefaultSOCKSPort, "SOCKS5 listen port (client only)")
	flag.StringVar(&cfg.dataDir, "data", session.DefaultDataDir, "Path to data directory")
	flag.StringVar(&cfg.dnsServer, "dns", session.DefaultDNSServer, "DNS server (for example 1.1.1.1:53)")
	flag.StringVar(&cfg.socksProxyAddr, "socks-proxy", "", "SOCKS5 proxy address for server egress")
	flag.IntVar(&cfg.socksProxyPort, "socks-proxy-port", 0, "SOCKS5 proxy port for server egress")
	flag.BoolVar(&cfg.debug, "debug", false, "Enable verbose logging")

	flag.Parse()

	return cfg
}

func configureLogging(debug bool) {
	if debug {
		logger.SetVerbose(true)
	}
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
