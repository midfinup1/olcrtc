package main

import (
	"context"
	"encoding/json"
	"flag"
	"fmt"
	"log"
	"strings"
	"sync"
	"time"

	"github.com/google/uuid"
	"github.com/gorilla/websocket"
	"github.com/pion/webrtc/v4"
)

type SignalMessage struct {
	CorrelationID string        `json:"correlationId"`
	Payload       SignalPayload `json:"payload"`
}

type SignalPayload struct {
	Type         string       `json:"@type"`
	SDP          string       `json:"sdp,omitempty"`
	Candidates   []SignalICE  `json:"candidates"`
	MediaState   MediaState   `json:"mediaState"`
	Subscription Subscription `json:"subscription"`
}

type SignalICE struct {
	Candidate         string  `json:"candidate"`
	SDPMLineIndex    *uint16 `json:"sdpMLineIndex"`
	SDPMid           string  `json:"sdpMid"`
	UsernameFragment *string `json:"usernameFragment"`
}

type MediaState struct {
	Audio          int `json:"audio"`
	SecondaryAudio int `json:"secondaryAudio"`
	Video          int `json:"video"`
	SecondaryVideo int `json:"secondaryVideo"`
}

type Subscription struct {
	Type           string   `json:"@type"`
	Audio          []string `json:"audio"`
	Video          []string `json:"video"`
	SecondaryVideo int      `json:"secondaryVideo"`
}

func main() {
	wsURL := flag.String("ws", "", "IVA websocket signalling URL")
	cookie := flag.String("cookie", "", "Cookie header copied from browser")
	flag.Parse()

	if strings.TrimSpace(*wsURL) == "" {
		log.Fatal("required: -ws wss://meet.iva360.ru/websocket/media/proxy/api/signalling/...")
	}

	ctx, cancel := context.WithTimeout(context.Background(), 90*time.Second)
	defer cancel()

	iceServers := []webrtc.ICEServer{
		{
			URLs:       []string{"turn:94.141.104.194:443?transport=tcp"},
			Username:   "ivcs",
			Credential: "ivcs",
		},
		{
			URLs:       []string{"turn:94.141.104.195:443?transport=tcp"},
			Username:   "ivcs",
			Credential: "ivcs",
		},
		{
			URLs:       []string{"turn:84.201.136.233:443?transport=tcp"},
			Username:   "ivcs",
			Credential: "ivcs",
		},
	}

	pc, err := webrtc.NewPeerConnection(webrtc.Configuration{
		ICEServers: iceServers,
	})
	if err != nil {
		log.Fatal(err)
	}
	defer func() {
		_ = pc.Close()
	}()

	_, err = pc.AddTransceiverFromKind(
		webrtc.RTPCodecTypeAudio,
		webrtc.RTPTransceiverInit{
			Direction: webrtc.RTPTransceiverDirectionRecvonly,
		},
	)
	if err != nil {
		log.Fatal("add audio transceiver: ", err)
	}

	iceConnected := make(chan struct{})
	pcConnected := make(chan struct{})
	dcOpened := make(chan struct{})
	dcClosed := make(chan struct{})
	done := make(chan struct{})

	var iceConnectedOnce sync.Once
	var pcConnectedOnce sync.Once
	var dcOpenedOnce sync.Once
	var dcClosedOnce sync.Once
	var doneOnce sync.Once

	closeDone := func() {
		doneOnce.Do(func() {
			close(done)
		})
	}

	pc.OnICEConnectionStateChange(func(state webrtc.ICEConnectionState) {
		fmt.Println("ICE state:", state.String())

		if state == webrtc.ICEConnectionStateConnected ||
			state == webrtc.ICEConnectionStateCompleted {
			iceConnectedOnce.Do(func() {
				close(iceConnected)
			})
		}

		if state == webrtc.ICEConnectionStateFailed ||
			state == webrtc.ICEConnectionStateDisconnected ||
			state == webrtc.ICEConnectionStateClosed {
			fmt.Println("ICE terminal/problem state:", state.String())
		}
	})

	pc.OnConnectionStateChange(func(state webrtc.PeerConnectionState) {
		fmt.Println("PeerConnection state:", state.String())

		if state == webrtc.PeerConnectionStateConnected {
			pcConnectedOnce.Do(func() {
				close(pcConnected)
			})
		}

		if state == webrtc.PeerConnectionStateFailed ||
			state == webrtc.PeerConnectionStateClosed {
			fmt.Println("PeerConnection terminal/problem state:", state.String())
			closeDone()
		}
	})

	pc.OnICECandidate(func(candidate *webrtc.ICECandidate) {
		if candidate == nil {
			fmt.Println("Local ICE gathering complete")
			return
		}

		fmt.Println("Local ICE candidate:", candidate.ToJSON().Candidate)
	})

	dc, err := pc.CreateDataChannel("data", nil)
	if err != nil {
		log.Fatal(err)
	}

	dc.OnOpen(func() {
		fmt.Println("===== DATACHANNEL OPENED =====")

		dcOpenedOnce.Do(func() {
			close(dcOpened)
		})

		if err := dc.SendText("hello from iva_probe"); err != nil {
			fmt.Println("DataChannel send error:", err)
			return
		}

		fmt.Println("Test message sent through DataChannel")
	})

	dc.OnMessage(func(msg webrtc.DataChannelMessage) {
		if msg.IsString {
			fmt.Println("DataChannel message:", string(msg.Data))
		} else {
			fmt.Println("DataChannel binary message bytes:", len(msg.Data))
		}
	})

	dc.OnClose(func() {
		fmt.Println("===== DATACHANNEL CLOSED =====")

		dcClosedOnce.Do(func() {
			close(dcClosed)
		})
	})

	dc.OnError(func(err error) {
		fmt.Println("===== DATACHANNEL ERROR =====")
		fmt.Println(err)
	})

	iceGatherDone := webrtc.GatheringCompletePromise(pc)

	offer, err := pc.CreateOffer(nil)
	if err != nil {
		log.Fatal(err)
	}

	if err := pc.SetLocalDescription(offer); err != nil {
		log.Fatal(err)
	}

	select {
	case <-iceGatherDone:
	case <-ctx.Done():
		log.Fatal("timeout while gathering ICE")
	}

	local := pc.LocalDescription()
	if local == nil {
		log.Fatal("local description is nil")
	}

	fmt.Println("===== LOCAL SDP CHECK =====")
	fmt.Println("m=audio:", strings.Contains(local.SDP, "m=audio"))
	fmt.Println("m=application:", strings.Contains(local.SDP, "m=application"))
	fmt.Println("a=sctp-port:", strings.Contains(local.SDP, "a=sctp-port"))

	headers := map[string][]string{
		"Origin":     {"https://meet.iva360.ru"},
		"User-Agent": {"Mozilla/5.0"},
	}

	if strings.TrimSpace(*cookie) != "" {
		headers["Cookie"] = []string{strings.TrimSpace(*cookie)}
	}

	conn, resp, err := websocket.DefaultDialer.Dial(*wsURL, headers)
	if err != nil {
		if resp != nil {
			fmt.Println("===== WEBSOCKET HANDSHAKE FAILED =====")
			fmt.Println("Status:", resp.Status)
			fmt.Println("StatusCode:", resp.StatusCode)
			fmt.Println("Headers:")
			for k, v := range resp.Header {
				fmt.Printf("%s: %v\n", k, v)
			}
		}
		log.Fatal(err)
	}
	defer func() {
		_ = conn.Close()
	}()

	msg := SignalMessage{
		CorrelationID: uuid.NewString(),
		Payload: SignalPayload{
			Type:       "negotiate",
			SDP:        local.SDP,
			Candidates: []SignalICE{},
			MediaState: MediaState{
				Audio:          -1,
				SecondaryAudio: -1,
				Video:          -1,
				SecondaryVideo: -1,
			},
			Subscription: Subscription{
				Type:           "streams",
				Audio:          []string{},
				Video:          []string{},
				SecondaryVideo: -1,
			},
		},
	}

	raw, err := json.Marshal(msg)
	if err != nil {
		log.Fatal(err)
	}

	fmt.Println("===== SENDING CORRELATION ID =====")
	fmt.Println(msg.CorrelationID)

	if err := conn.WriteMessage(websocket.TextMessage, raw); err != nil {
		log.Fatal(err)
	}

	var answer SignalMessage
	var answerBody []byte

	for {
		_, body, err := conn.ReadMessage()
		if err != nil {
			log.Fatal(err)
		}

		text := string(body)

		fmt.Println("===== IVA RESPONSE =====")
		fmt.Println(text)

		if !strings.Contains(text, msg.CorrelationID) {
			continue
		}

		answerBody = body

		fmt.Println("===== MATCHED RESPONSE =====")
		fmt.Println("m=audio:", strings.Contains(text, "m=audio"))
		fmt.Println("m=application:", strings.Contains(text, "m=application"))
		fmt.Println("a=sctp-port:", strings.Contains(text, "a=sctp-port"))
		fmt.Println("a=inactive:", strings.Contains(text, "a=inactive"))

		break
	}

	if err := json.Unmarshal(answerBody, &answer); err != nil {
		log.Fatal("parse IVA answer: ", err)
	}

	if strings.TrimSpace(answer.Payload.SDP) == "" {
		log.Fatal("IVA answer SDP is empty")
	}

	fmt.Println("===== SET REMOTE DESCRIPTION =====")

	if err := pc.SetRemoteDescription(webrtc.SessionDescription{
		Type: webrtc.SDPTypeAnswer,
		SDP:  answer.Payload.SDP,
	}); err != nil {
		log.Fatal("SetRemoteDescription failed: ", err)
	}

	fmt.Println("===== ADD IVA CANDIDATES =====")

	for _, c := range answer.Payload.Candidates {
		if strings.TrimSpace(c.Candidate) == "" {
			continue
		}

		candidate := webrtc.ICECandidateInit{
			Candidate:     c.Candidate,
			SDPMid:        &c.SDPMid,
			SDPMLineIndex: c.SDPMLineIndex,
		}

		if err := pc.AddICECandidate(candidate); err != nil {
			fmt.Println("AddICECandidate error:", err)
			fmt.Println("Candidate:", c.Candidate)
		} else {
			fmt.Println("Remote ICE candidate added:", c.Candidate)
		}
	}

	fmt.Println("===== WAITING FOR ICE CONNECTED =====")

	select {
	case <-iceConnected:
		fmt.Println("===== ICE CONNECTED =====")
	case <-time.After(45 * time.Second):
		log.Fatal("timeout waiting for ICE connected")
	case <-done:
		log.Fatal("connection closed before ICE connected")
	}

	fmt.Println("===== WAITING FOR PEER CONNECTION CONNECTED =====")

	select {
	case <-pcConnected:
		fmt.Println("===== PEER CONNECTION CONNECTED =====")
	case <-time.After(15 * time.Second):
		fmt.Println("PeerConnection connected timeout, but ICE is already connected. Continue waiting for DataChannel.")
	case <-done:
		log.Fatal("connection closed before PeerConnection connected")
	}

	fmt.Println("===== WAITING FOR DATACHANNEL OPEN =====")

	select {
	case <-dcOpened:
		fmt.Println("===== SUCCESS: DATACHANNEL WORKS THROUGH IVA =====")
	case <-time.After(45 * time.Second):
		log.Fatal("timeout waiting for DataChannel open")
	case <-done:
		log.Fatal("connection closed before DataChannel open")
	}

	fmt.Println("===== KEEPING CONNECTION FOR 20 SECONDS =====")

	select {
	case <-time.After(20 * time.Second):
		fmt.Println("Done.")
	case <-dcClosed:
		fmt.Println("DataChannel closed.")
	case <-done:
		fmt.Println("Connection closed.")
	}
}