// Package session wires runtime configuration to application mode entrypoints.
package session

import (
	"context"
	"errors"
	"fmt"

	"github.com/openlibrecommunity/olcrtc/internal/carrier"
	"github.com/openlibrecommunity/olcrtc/internal/carrier/builtin"
	"github.com/openlibrecommunity/olcrtc/internal/client"
	"github.com/openlibrecommunity/olcrtc/internal/link"
	"github.com/openlibrecommunity/olcrtc/internal/link/direct"
	"github.com/openlibrecommunity/olcrtc/internal/server"
	"github.com/openlibrecommunity/olcrtc/internal/transport"
	"github.com/openlibrecommunity/olcrtc/internal/transport/datachannel"
)

const (
	ModeServer = "srv"
	ModeClient = "cnc"

	CarrierJazz     = "jazz"
	CarrierWBStream = "wbstream"

	DefaultLink      = "direct"
	DefaultTransport = "datachannel"
	DefaultDNSServer = "1.1.1.1:53"
	DefaultDataDir   = "data"
	DefaultSOCKSHost = "127.0.0.1"
	DefaultSOCKSPort = 8808
)

var (
	ErrRoomIDRequired       = errors.New("room ID required (use -id <id>)")
	ErrModeRequired         = errors.New("mode required (use -mode srv or -mode cnc)")
	ErrCarrierRequired      = errors.New("carrier required (use -carrier jazz or -carrier wbstream)")
	ErrUnsupportedCarrier   = errors.New("unsupported carrier")
	ErrUnsupportedLink      = errors.New("unsupported link")
	ErrUnsupportedTransport = errors.New("unsupported transport")
	ErrLinkRequired         = errors.New("link required (use -link direct)")
	ErrTransportRequired    = errors.New("transport required (use -transport datachannel)")
	ErrKeyRequired          = errors.New("key required (use -key <hex>)")
	ErrDNSServerRequired    = errors.New("dns server required (use -dns 1.1.1.1:53)")
	ErrSOCKSHostRequired    = errors.New("socks host required for cnc mode (use -socks-host)")
	ErrSOCKSPortRequired    = errors.New("socks port required for cnc mode (use -socks-port)")
)

type Config struct {
	Mode           string
	Link           string
	Transport      string
	Carrier        string
	RoomID         string
	KeyHex         string
	SOCKSHost      string
	SOCKSPort      int
	DNSServer      string
	SOCKSProxyAddr string
	SOCKSProxyPort int
}

func RegisterDefaults() {
	builtin.Register()
	link.Register(DefaultLink, direct.New)
	transport.Register(DefaultTransport, datachannel.New)
}

func Validate(cfg Config) error {
	if cfg.Mode == "" || (cfg.Mode != ModeServer && cfg.Mode != ModeClient) {
		return ErrModeRequired
	}

	if cfg.Carrier == "" {
		return ErrCarrierRequired
	}
	if cfg.Carrier != CarrierJazz && cfg.Carrier != CarrierWBStream {
		return fmt.Errorf("%w: %s (available: %v)", ErrUnsupportedCarrier, cfg.Carrier, carrier.Available())
	}

	if cfg.Link == "" {
		return ErrLinkRequired
	}
	if cfg.Link != DefaultLink {
		return fmt.Errorf("%w: %s (available: %v)", ErrUnsupportedLink, cfg.Link, link.Available())
	}

	if cfg.Transport == "" {
		return ErrTransportRequired
	}
	if cfg.Transport != DefaultTransport {
		return fmt.Errorf("%w: %s (available: %v)", ErrUnsupportedTransport, cfg.Transport, transport.Available())
	}

	if cfg.RoomID == "" && cfg.Carrier != CarrierJazz {
		return ErrRoomIDRequired
	}

	if cfg.KeyHex == "" {
		return ErrKeyRequired
	}

	if cfg.DNSServer == "" {
		return ErrDNSServerRequired
	}

	if cfg.Mode == ModeClient {
		if cfg.SOCKSHost == "" {
			return ErrSOCKSHostRequired
		}
		if cfg.SOCKSPort == 0 {
			return ErrSOCKSPortRequired
		}
	}

	return nil
}

func Run(ctx context.Context, cfg Config) error {
	roomURL := buildRoomURL(cfg.Carrier, cfg.RoomID)

	switch cfg.Mode {
	case ModeServer:
		return server.Run(
			ctx,
			cfg.Link,
			cfg.Transport,
			cfg.Carrier,
			roomURL,
			cfg.KeyHex,
			cfg.DNSServer,
			cfg.SOCKSProxyAddr,
			cfg.SOCKSProxyPort,
		)
	case ModeClient:
		return client.Run(
			ctx,
			cfg.Link,
			cfg.Transport,
			cfg.Carrier,
			roomURL,
			cfg.KeyHex,
			fmt.Sprintf("%s:%d", cfg.SOCKSHost, cfg.SOCKSPort),
			cfg.DNSServer,
			"",
			"",
		)
	default:
		return ErrModeRequired
	}
}

func buildRoomURL(carrierName, roomID string) string {
	if carrierName == CarrierJazz && roomID == "" {
		return "any"
	}
	return roomID
}
