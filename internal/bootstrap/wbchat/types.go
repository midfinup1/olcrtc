package wbchat

type ChatInfo struct {
	ChatToken          string `json:"chatToken"`
	ChatID             int64  `json:"chatId"`
	LastReadMessageID  int64  `json:"lastReadMessageId"`
	UnreadMessageCount string `json:"unreadMessageCount"`
	IsMuted            bool   `json:"isMuted"`
	IsViewer           bool   `json:"isViewer"`
}

type ChatMessage struct {
	ID        int64      `json:"id"`
	ChatID    int64      `json:"chatId"`
	Text      string     `json:"text"`
	Author    ChatAuthor `json:"author"`
	CreatedAt string     `json:"createdAt"`
	UpdatedAt string     `json:"updatedAt"`
}

type ChatAuthor struct {
	ID          string `json:"id"`
	DisplayName string `json:"displayName"`
	IsViewer    bool   `json:"isViewer"`
}

type MessagesResponse struct {
	Messages []ChatMessage `json:"messages"`
}

type connectionTokenResponse struct {
	ConnectionToken string `json:"connectionToken"`
}

type guestRegisterRequest struct {
	DisplayName string `json:"displayName"`
	Device      device `json:"device"`
}

type device struct {
	DeviceName string `json:"deviceName"`
	DeviceType string `json:"deviceType"`
}

type guestRegisterResponse struct {
	AccessToken string `json:"accessToken"`
}

type wsFrame struct {
	ID        int64      `json:"id,omitempty"`
	Connect  any        `json:"connect,omitempty"`
	Subscribe any       `json:"subscribe,omitempty"`
	Publish  *wsPublish `json:"publish,omitempty"`
	Push      *wsPush    `json:"push,omitempty"`
	Error     any        `json:"error,omitempty"`
}

type wsPublish struct {
	Channel string      `json:"channel,omitempty"`
	Data    interface{} `json:"data,omitempty"`
}

type wsPush struct {
	Channel string `json:"channel"`
	Pub     wsPub  `json:"pub"`
}

type wsPub struct {
	Data wsEventData `json:"data"`
}

type wsEventData struct {
	Type    string         `json:"type"`
	Payload map[string]any `json:"payload"`
}

type sendMessageData struct {
	Type    string             `json:"type"`
	Payload sendMessagePayload `json:"payload"`
}

type sendMessagePayload struct {
	TextPayload textPayload `json:"textPayload"`
}

type textPayload struct {
	Text string `json:"text"`
}