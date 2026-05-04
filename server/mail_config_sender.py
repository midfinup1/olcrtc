#!/usr/bin/env python3

import json
import smtplib
import ssl
from datetime import datetime, timezone
from email.message import EmailMessage
from pathlib import Path


SETTINGS_FILE = Path("/root/olcrtc/server/mail_settings.env")


def parse_env_file(path: Path) -> dict:
    data = {}

    if not path.exists():
        raise RuntimeError(f"settings file not found: {path}")

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()

        if not line or line.startswith("#") or "=" not in line:
            continue

        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()

        if len(value) >= 2 and value[0] == '"' and value[-1] == '"':
            value = value[1:-1]

        if len(value) >= 2 and value[0] == "'" and value[-1] == "'":
            value = value[1:-1]

        data[key] = value

    return data


def read_recipients(path: Path) -> list[str]:
    if not path.exists():
        raise RuntimeError(f"recipients file not found: {path}")

    recipients = []

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()

        if not line or line.startswith("#"):
            continue

        recipients.append(line)

    if not recipients:
        raise RuntimeError("recipients list is empty")

    return recipients


def connection_env_to_json(path: Path) -> dict:
    env = parse_env_file(path)

    provider = env.get("PROVIDER", "")
    room_id = env.get("ROOM_ID", "")
    encryption_key = env.get("ENCRYPTION_KEY", "")
    transport_type = env.get("TRANSPORT_TYPE", "datachannel")
    dns_server = env.get("DNS_SERVER", "1.1.1.1:53")

    if not provider:
        raise RuntimeError("PROVIDER is missing in connection.env")

    if not room_id:
        raise RuntimeError("ROOM_ID is missing in connection.env")

    if not encryption_key:
        raise RuntimeError("ENCRYPTION_KEY is missing in connection.env")

    return {
        "provider": provider,
        "room_id": room_id,
        "encryption_key": encryption_key,
        "transport_type": transport_type,
        "dns_server": dns_server,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }


def build_message(mail_from: str, recipient: str, config: dict) -> EmailMessage:
    msg = EmailMessage()

    msg["From"] = mail_from
    msg["To"] = recipient
    msg["Subject"] = "OLCRTC_CONFIG"

    config_json = json.dumps(config, ensure_ascii=False, indent=2)

    text = (
        "OLCRTC_CONFIG\n\n"
        "Актуальные данные подключения olcRTC:\n\n"
        f"{config_json}\n\n"
        "Используйте самое свежее письмо с темой OLCRTC_CONFIG.\n"
    )

    msg.set_content(text)

    msg.add_attachment(
        config_json.encode("utf-8"),
        maintype="application",
        subtype="json",
        filename="connection.json",
    )

    return msg


def send_email(settings: dict, recipients: list[str], config: dict):
    smtp_host = settings.get("SMTP_HOST", "smtp.yandex.ru")
    smtp_port = int(settings.get("SMTP_PORT", "465"))
    smtp_user = settings["SMTP_USER"]
    smtp_password = settings["SMTP_PASSWORD"]
    mail_from = settings.get("MAIL_FROM", smtp_user)

    context = ssl.create_default_context()

    with smtplib.SMTP_SSL(smtp_host, smtp_port, context=context, timeout=30) as server:
        server.login(smtp_user, smtp_password)

        for recipient in recipients:
            msg = build_message(mail_from, recipient, config)
            server.send_message(msg)
            print(f"sent to {recipient}")


def main():
    settings = parse_env_file(SETTINGS_FILE)

    recipients_file = Path(settings.get("RECIPIENTS_FILE", "/root/olcrtc/server/mail_recipients.txt"))
    connection_file = Path(settings.get("CONNECTION_FILE", "/root/olcrtc/connection.env"))

    recipients = read_recipients(recipients_file)
    config = connection_env_to_json(connection_file)

    send_email(settings, recipients, config)


if __name__ == "__main__":
    main()