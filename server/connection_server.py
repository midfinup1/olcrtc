#!/usr/bin/env python3

import json
import os
from pathlib import Path
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


HOST = "0.0.0.0"
PORT = 8090

CONNECTION_FILE = Path("/root/olcrtc/connection.env")

API_TOKEN = os.environ.get(
    "OLCRTC_CONNECTION_TOKEN",
    "3311fe77453c1f36d1ad8535470681595c7bf019cf7831a1797e9ce863932973",
)


def parse_env_file(path: Path) -> dict:
    data = {}

    if not path.exists():
        raise RuntimeError(f"connection file not found: {path}")

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()

        if not line:
            continue

        if line.startswith("#"):
            continue

        if "=" not in line:
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


def load_connection_config() -> dict:
    env = parse_env_file(CONNECTION_FILE)

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
    }


class Handler(BaseHTTPRequestHandler):
    def log_message(self, format_string, *args):
        print(
            f"{self.client_address[0]} - - "
            f"[{self.log_date_time_string()}] {format_string % args}"
        )

    def send_json(self, status_code: int, payload: dict):
        body = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")

        self.send_response(status_code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def send_text(self, status_code: int, text: str):
        body = text.encode("utf-8")

        self.send_response(status_code)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def check_auth(self) -> bool:
        if not API_TOKEN:
            return True

        auth_header = self.headers.get("Authorization", "")

        expected = f"Bearer {API_TOKEN}"

        return auth_header == expected

    def do_GET(self):
        if self.path not in ["/connection.json", "/"]:
            self.send_json(
                404,
                {
                    "ok": False,
                    "error": "not found",
                },
            )
            return

        if not self.check_auth():
            self.send_json(
                401,
                {
                    "ok": False,
                    "error": "unauthorized",
                },
            )
            return

        try:
            config = load_connection_config()
            self.send_json(200, config)

        except Exception as exc:
            self.send_json(
                500,
                {
                    "ok": False,
                    "error": f"{type(exc).__name__}: {exc}",
                },
            )


def main():
    server = ThreadingHTTPServer((HOST, PORT), Handler)
    server.timeout = 10

    print(f"Serving connection data on http://{HOST}:{PORT}/connection.json")
    print(f"Connection file: {CONNECTION_FILE}")
    print(f"Token enabled: {'yes' if API_TOKEN else 'no'}")

    server.serve_forever()


if __name__ == "__main__":
    main()