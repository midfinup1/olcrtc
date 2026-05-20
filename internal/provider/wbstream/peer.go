// Package wbstream implements the WB Stream WebRTC provider.
package wbstream

import (
	"context"
	"errors"
	"fmt"
	"log"
	"strings"
	"sync"
	"sync/atomic"
	"time"

	lksdk "github.com/livekit/server-sdk-go/v2"
	"github.com/pion/webrtc/v4"
)

const (
	defaultWSURL = "wss://wbstream01-el.wb.ru:7880"
)

var (
	ErrPeerClosed           = errors.New("peer closed")
	ErrSendQueueFull       = errors.New("send queue full")
	ErrLiveKitNotConnected = errors.New("livekit room not connected")
)

type Peer struct {
	roomURL         string
	name            string
	room            *lksdk.Room
	onData          func([]byte)
	onReconnect     func(*webrtc.DataChannel)
	shouldReconnect func() bool
	onEnded         func(string)
	sendQueue       chan []byte
	closed          atomic.Bool
	done            chan struct{}
	cancel          context.CancelFunc
	videoTrackMu    sync.RWMutex
	videoTracks     []webrtc.TrackLocal
	onVideoTrack    func(*webrtc.TrackRemote, *webrtc.RTPReceiver)
	wg              sync.WaitGroup
}

func NewPeer(ctx context.Context, roomURL, name string, onData func([]byte)) (*Peer, error) {
	_, cancel := context.WithCancel(ctx)

	return &Peer{
		roomURL:   roomURL,
		name:      name,
		onData:    onData,
		sendQueue: make(chan []byte, 5000),
		done:      make(chan struct{}),
		cancel:    cancel,
	}, nil
}

func (p *Peer) Connect(ctx context.Context) error {
	token, serverURL, err := p.getRoomConnection(ctx)
	if err != nil {
		return fmt.Errorf("get room token: %w", err)
	}

	if strings.TrimSpace(serverURL) == "" {
		serverURL = defaultWSURL
	}

	roomCB := &lksdk.RoomCallback{
		ParticipantCallback: lksdk.ParticipantCallback{
			OnDataReceived: func(data []byte, _ lksdk.DataReceiveParams) {
				if p.onData != nil {
					p.onData(data)
				}
			},
			OnTrackSubscribed: func(track *webrtc.TrackRemote, _ *lksdk.RemoteTrackPublication, _ *lksdk.RemoteParticipant) {
				if track.Kind() != webrtc.RTPCodecTypeVideo {
					return
				}

				p.videoTrackMu.RLock()
				cb := p.onVideoTrack
				p.videoTrackMu.RUnlock()

				if cb != nil {
					cb(track, nil)
				}
			},
		},
		OnDisconnected: func() {
			if p.onEnded != nil {
				p.onEnded("disconnected from livekit")
			}
		},
	}

	log.Printf("WB Stream connecting LiveKit server=%s room=%s", serverURL, p.roomURL)

	room, err := lksdk.ConnectToRoomWithToken(serverURL, token, roomCB, lksdk.WithAutoSubscribe(true))
	if err != nil {
		return fmt.Errorf("connect to room: %w", err)
	}

	p.room = room

	if err := p.publishPendingTracks(); err != nil {
		return err
	}

	p.wg.Add(1)
	go p.processSendQueue()

	return nil
}

func (p *Peer) publishPendingTracks() error {
	p.videoTrackMu.RLock()
	defer p.videoTrackMu.RUnlock()

	for _, track := range p.videoTracks {
		if _, err := p.room.LocalParticipant.PublishTrack(track, &lksdk.TrackPublicationOptions{
			Name: "videochannel",
		}); err != nil {
			return fmt.Errorf("failed to publish track: %w", err)
		}
	}

	return nil
}

func (p *Peer) getRoomConnection(ctx context.Context) (string, string, error) {
	accessToken, err := registerGuest(ctx, p.name)
	if err != nil {
		return "", "", fmt.Errorf("register guest: %w", err)
	}

	roomID := strings.TrimSpace(p.roomURL)

	if roomID == "" || roomID == "any" {
		roomID, err = createRoom(ctx, accessToken)
		if err != nil {
			return "", "", fmt.Errorf("create room: %w", err)
		}

		log.Printf("WB Stream room created: %s", roomID)
		log.Printf("To connect client use: -id %s", roomID)
	} else {
		if err := joinRoom(ctx, accessToken, roomID); err != nil {
			if isWBRoomNotFoundError(err) {
				log.Printf("WB Stream fixed room not found, trying to recreate room_id=%s", roomID)

				createdRoomID, createErr := createRoom(ctx, accessToken, roomID)
				if createErr != nil {
					return "", "", fmt.Errorf("recreate fixed room failed room_id=%s: %w", roomID, createErr)
				}

				if createdRoomID != roomID {
					return "", "", fmt.Errorf("recreate fixed room returned different id: want=%s got=%s", roomID, createdRoomID)
				}

				time.Sleep(750 * time.Millisecond)

				if joinErr := joinRoom(ctx, accessToken, roomID); joinErr != nil {
					return "", "", fmt.Errorf("join recreated fixed room failed room_id=%s: %w", roomID, joinErr)
				}

				log.Printf("WB Stream fixed room recreated and joined: %s", roomID)
			} else {
				return "", "", fmt.Errorf("join room: %w", err)
			}
		}
	}

	token, serverURL, err := getConnectionDetails(ctx, accessToken, roomID, p.name)
	if err == nil {
		return token, serverURL, nil
	}

	log.Printf("WB Stream connection-details failed, trying legacy token endpoint: %v", err)

	token, err = getToken(ctx, accessToken, roomID, p.name)
	if err != nil {
		return "", "", fmt.Errorf("get token: %w", err)
	}

	return token, defaultWSURL, nil
}

func (p *Peer) processSendQueue() {
	defer p.wg.Done()

	for {
		select {
		case <-p.done:
			return

		case data, ok := <-p.sendQueue:
			if !ok {
				return
			}

			if p.room == nil || p.room.LocalParticipant == nil {
				log.Printf("WB Stream publish data error: %v", ErrLiveKitNotConnected)
				continue
			}

			if err := p.room.LocalParticipant.PublishDataPacket(
				lksdk.UserData(data),
				lksdk.WithDataPublishTopic("olcrtc"),
				lksdk.WithDataPublishReliable(true),
			); err != nil {
				log.Printf("WB Stream publish data error: %v", err)
			}
		}
	}
}

func (p *Peer) Send(data []byte) error {
	if p.closed.Load() {
		return ErrPeerClosed
	}

	select {
	case p.sendQueue <- data:
		return nil

	default:
		return ErrSendQueueFull
	}
}

func (p *Peer) Close() error {
	if p.closed.CompareAndSwap(false, true) {
		p.cancel()
		close(p.done)

		if p.room != nil {
			p.room.Disconnect()
		}

		close(p.sendQueue)
		p.wg.Wait()
	}

	return nil
}

func (p *Peer) SetReconnectCallback(cb func(*webrtc.DataChannel)) {
	p.onReconnect = cb
}

func (p *Peer) SetShouldReconnect(fn func() bool) {
	p.shouldReconnect = fn
}

func (p *Peer) SetEndedCallback(cb func(string)) {
	p.onEnded = cb
}

func (p *Peer) WatchConnection(_ context.Context) {}

func (p *Peer) CanSend() bool {
	return !p.closed.Load() && p.room != nil
}

func (p *Peer) GetSendQueue() chan []byte {
	return p.sendQueue
}

func (p *Peer) GetBufferedAmount() uint64 {
	return 0
}

func (p *Peer) AddVideoTrack(track webrtc.TrackLocal) error {
	p.videoTrackMu.Lock()
	p.videoTracks = append(p.videoTracks, track)
	p.videoTrackMu.Unlock()

	if p.room == nil || p.room.LocalParticipant == nil {
		return nil
	}

	if _, err := p.room.LocalParticipant.PublishTrack(track, &lksdk.TrackPublicationOptions{
		Name: "videochannel",
	}); err != nil {
		return fmt.Errorf("failed to publish track: %w", err)
	}

	return nil
}

func (p *Peer) SetVideoTrackHandler(cb func(*webrtc.TrackRemote, *webrtc.RTPReceiver)) {
	p.videoTrackMu.Lock()
	defer p.videoTrackMu.Unlock()

	p.onVideoTrack = cb
}