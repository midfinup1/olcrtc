package main

import (
	"context"
	"log"
	"time"

	"github.com/openlibrecommunity/olcrtc/internal/bootstrap/wbchat"
)

func main() {
	token := "eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9.eyJpYXQiOjE3NzkyNTQ1NzUsInVzZXIiOiIxMDQzNTI2NTAiLCJzaGFyZF9rZXkiOiI2IiwiY2xpZW50X2lkIjoic3RyZWFtIiwic2Vzc2lvbl9pZCI6IjllMDJmMjE5ODkxMTRmYzRiMGE3NzY3MTk1YzI0OTMyIiwidmFsaWRhdGlvbl9rZXkiOiI1YWU1MjU0MWZiMTlmYzQ3OGNhNDYyYjc0ZTQ4YmNhYTdhYjc5NTA0M2RhYzU3YzU5YWEzN2E1OWNjODBmYWQ5IiwidXNlcl9yZWdpc3RyYXRpb25fZHQiOjE2NzY3MTkxMTIsInZlcnNpb24iOjJ9.YcM-PNjcMK3nXTd3qiREqtUN_8KIDwbVDzJmLDS-pXCFUpA7U3wk9jGWPdMnkS9okCALHT8HOgQz7MQqrTikYIoTyayISfIgY49NJwFwORNGDdeEGOOAWlSRMi9iGmSxml1TNDT0RGhmYbniHGkz9FeQ_axcpAyC9Zbe1O4ldu1tUo-ZItW3ADWlxxEsVyOekkxMIf_1GZ_XLUY0ggh2JHIpBdRjbJn6WLdhINUeHGzA4uwfBvr7xM0tnD-QZi4zelTR9u4JkVqzw9Ub8FZmUEKi-POLtegRACODnStE13dMYipdDHGl8zpihXvItItj1S7fFsqOQ0ThBjhgVdg0-A"
	if token == "" {
		log.Fatal("WB_ACCESS_TOKEN is empty")
	}

	ctx, cancel := context.WithTimeout(context.Background(), 60*time.Second)
	defer cancel()

	roomID := "bb_bootstrap_main"
	displayName := "BareBone Test"

	client := wbchat.NewClient(token)

	chat, err := client.GetChat(ctx, roomID, displayName)
	if err != nil {
		log.Fatalf("get chat failed: %v", err)
	}

	log.Printf("chat_id=%d", chat.ChatID)

	conn, err := client.ConnectWebSocket(ctx, roomID)
	if err != nil {
		log.Fatalf("connect ws failed: %v", err)
	}

	defer func() {
		_ = conn.Close()
	}()

	log.Printf("websocket connected")

	if err := client.SubscribeChatWS(ctx, conn, chat.ChatID, chat.ChatToken); err != nil {
		log.Fatalf("subscribe failed: %v", err)
	}

	log.Printf("subscribed")

	go func() {
		err := client.ReadLoop(ctx, conn, func(msg wbchat.ChatMessage) {
			log.Printf("message created id=%d chat_id=%d text=%q", msg.ID, msg.ChatID, msg.Text)
		}, func(raw []byte) {
			log.Printf("raw ws: %s", raw)
		})

		if err != nil {
			log.Printf("read loop error: %v", err)
		}
	}()

	time.Sleep(500 * time.Millisecond)

	if err := client.SendTextWS(ctx, conn, chat.ChatID, "bb-go-test-message"); err != nil {
		log.Fatalf("send failed: %v", err)
	}

	log.Printf("sent")

	<-ctx.Done()
}