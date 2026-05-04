package transport

import (
	"context"
	"fmt"
	"sort"
)

type Config struct {
	Name      string
	Carrier   string
	RoomURL   string
	OnData    func([]byte)
	DNSServer string
	ProxyAddr string
	ProxyPort int
}

type Features struct {
	Reliable        bool
	Ordered         bool
	MessageOriented bool
	MaxPayloadSize  int
}

type Transport interface {
	Connect(ctx context.Context) error
	Send([]byte) error
	CanSend() bool
	Close() error
	
	WatchConnection(ctx context.Context)
	SetReconnectCallback(func())
	SetShouldReconnect(func() bool)
	SetEndedCallback(func(string))
	Features() Features
}

type Factory func(context.Context, Config) (Transport, error)

var factories = map[string]Factory{}

func Register(name string, factory Factory) {
	factories[name] = factory
}

func New(ctx context.Context, name string, cfg Config) (Transport, error) {
	factory, ok := factories[name]
	if !ok {
		return nil, fmt.Errorf("unknown transport: %s", name)
	}

	cfg.Name = name
	return factory(ctx, cfg)
}

func Available() []string {
	names := make([]string, 0, len(factories))

	for name := range factories {
		names = append(names, name)
	}

	sort.Strings(names)

	return names
}