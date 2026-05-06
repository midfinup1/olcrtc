import http.server
import select
import socket
import socketserver
import subprocess
import threading
import urllib.parse
import winreg

from common import PlatformAdapter, run_app, run_command


HTTP_PROXY_PORT_OFFSET = 1


def _recv_exact(sock: socket.socket, size: int) -> bytes:
    data = b""

    while len(data) < size:
        chunk = sock.recv(size - len(data))

        if not chunk:
            raise ConnectionError("unexpected EOF while reading socket")

        data += chunk

    return data


def _socks5_connect(
    socks_host: str,
    socks_port: int,
    target_host: str,
    target_port: int,
) -> socket.socket:
    target_host = target_host.strip()

    if not target_host:
        raise ConnectionError("target host is empty")

    s = socket.create_connection((socks_host, socks_port), timeout=15)
    s.settimeout(30)

    try:
        s.sendall(b"\x05\x01\x00")

        resp = _recv_exact(s, 2)

        if resp != b"\x05\x00":
            raise ConnectionError(f"SOCKS5 handshake failed: {resp!r}")

        host_bytes = target_host.encode("idna")

        if len(host_bytes) > 255:
            raise ConnectionError("target host is too long for SOCKS5 domain request")

        request = (
            b"\x05\x01\x00\x03"
            + bytes([len(host_bytes)])
            + host_bytes
            + int(target_port).to_bytes(2, "big")
        )

        s.sendall(request)

        header = _recv_exact(s, 4)

        if header[0] != 0x05:
            raise ConnectionError(f"invalid SOCKS5 response version: {header!r}")

        if header[1] != 0x00:
            raise ConnectionError(f"SOCKS5 CONNECT failed, code={header[1]}")

        address_type = header[3]

        if address_type == 0x01:
            _recv_exact(s, 4)
            _recv_exact(s, 2)
        elif address_type == 0x03:
            length = _recv_exact(s, 1)[0]
            _recv_exact(s, length)
            _recv_exact(s, 2)
        elif address_type == 0x04:
            _recv_exact(s, 16)
            _recv_exact(s, 2)
        else:
            raise ConnectionError(f"unknown SOCKS5 address type: {address_type}")

        s.settimeout(None)
        return s

    except Exception:
        try:
            s.close()
        except OSError:
            pass
        raise


def _relay_bidirectional(left: socket.socket, right: socket.socket):
    sockets = [left, right]

    for sock in sockets:
        sock.setblocking(False)

    try:
        while True:
            readable, _, errored = select.select(sockets, [], sockets, 60)

            if errored:
                return

            if not readable:
                return

            for sock in readable:
                other = right if sock is left else left

                try:
                    data = sock.recv(65536)

                    if not data:
                        return

                    other.sendall(data)

                except OSError:
                    return

    finally:
        for sock in sockets:
            try:
                sock.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass

            try:
                sock.close()
            except OSError:
                pass


def _split_host_port(value: str, default_port: int) -> tuple[str, int]:
    value = value.strip()

    if not value:
        raise ValueError("empty host")

    if value.startswith("["):
        end = value.find("]")

        if end == -1:
            raise ValueError(f"invalid IPv6 host: {value}")

        host = value[1:end]
        rest = value[end + 1 :]

        if rest.startswith(":"):
            return host, int(rest[1:])

        return host, default_port

    if ":" in value:
        host, port_text = value.rsplit(":", 1)

        if port_text.isdigit():
            return host, int(port_text)

    return value, default_port


def _origin_form_from_proxy_path(path: str) -> str:
    parsed = urllib.parse.urlsplit(path)

    if parsed.scheme and parsed.netloc:
        result = urllib.parse.urlunsplit(
            (
                "",
                "",
                parsed.path or "/",
                parsed.query,
                "",
            )
        )
        return result or "/"

    return path or "/"


class _SocksProxyHandler(http.server.BaseHTTPRequestHandler):
    socks_host: str = "127.0.0.1"
    socks_port: int = 8808

    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *args):
        pass

    def do_CONNECT(self):
        try:
            host, port = _split_host_port(self.path, 443)

            upstream = _socks5_connect(
                self.socks_host,
                self.socks_port,
                host,
                port,
            )

            self.send_response(200, "Connection Established")
            self.end_headers()

            _relay_bidirectional(self.connection, upstream)

        except Exception as exc:
            try:
                self.send_error(502, f"SOCKS5 tunnel failed: {exc}")
            except OSError:
                pass

    def _do_http(self):
        try:
            host_header = self.headers.get("Host", "")

            if not host_header:
                self.send_error(400, "Host header is required")
                return

            host, port = _split_host_port(host_header, 80)

            upstream = _socks5_connect(
                self.socks_host,
                self.socks_port,
                host,
                port,
            )

            content_length = int(self.headers.get("Content-Length", "0") or "0")
            body = self.rfile.read(content_length) if content_length else b""

            origin_path = _origin_form_from_proxy_path(self.path)

            request_line = f"{self.command} {origin_path} {self.request_version}\r\n"

            headers = []

            for key, value in self.headers.items():
                if key.lower() in [
                    "proxy-connection",
                    "proxy-authenticate",
                    "proxy-authorization",
                    "connection",
                ]:
                    continue

                headers.append(f"{key}: {value}\r\n")

            headers.append("Connection: close\r\n")

            raw_request = (
                request_line.encode("utf-8")
                + "".join(headers).encode("utf-8")
                + b"\r\n"
                + body
            )

            upstream.sendall(raw_request)

            _relay_bidirectional(self.connection, upstream)

        except Exception as exc:
            try:
                self.send_error(502, f"HTTP proxy failed: {exc}")
            except OSError:
                pass

    do_GET = _do_http
    do_POST = _do_http
    do_PUT = _do_http
    do_DELETE = _do_http
    do_PATCH = _do_http
    do_HEAD = _do_http
    do_OPTIONS = _do_http


class _ThreadedHTTPProxy(socketserver.ThreadingMixIn, http.server.HTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, host: str, port: int, socks_host: str, socks_port: int):
        handler = type(
            "_Handler",
            (_SocksProxyHandler,),
            {
                "socks_host": socks_host,
                "socks_port": socks_port,
            },
        )

        super().__init__((host, port), handler)


class HttpProxyBridge:
    def __init__(self, socks_host: str, socks_port: int, http_port: int):
        self.socks_host = socks_host
        self.socks_port = socks_port
        self.http_port = http_port
        self._server: _ThreadedHTTPProxy | None = None
        self._thread: threading.Thread | None = None

    def start(self):
        if self._server is not None:
            return

        self._server = _ThreadedHTTPProxy(
            "127.0.0.1",
            self.http_port,
            self.socks_host,
            self.socks_port,
        )

        self._thread = threading.Thread(
            target=self._server.serve_forever,
            daemon=True,
            name="http-proxy-bridge",
        )

        self._thread.start()

    def stop(self):
        if self._server is not None:
            try:
                self._server.shutdown()
            except OSError:
                pass

            try:
                self._server.server_close()
            except OSError:
                pass

            self._server = None

        self._thread = None

    @property
    def address(self) -> str:
        return f"127.0.0.1:{self.http_port}"


def _refresh_wininet():
    cmd = (
        "$sig='[DllImport(\"wininet.dll\",SetLastError=true)]"
        "public static extern bool InternetSetOption(IntPtr h,int d,IntPtr b,int l);';"
        "$t=Add-Type -MemberDefinition $sig -Name WinInet -Namespace N -PassThru;"
        "$t::InternetSetOption([IntPtr]::Zero,39,[IntPtr]::Zero,0)|Out-Null;"
        "$t::InternetSetOption([IntPtr]::Zero,37,[IntPtr]::Zero,0)|Out-Null;"
    )

    run_command(
        [
            "powershell",
            "-NoProfile",
            "-Command",
            cmd,
        ],
        timeout=10,
        windows_no_window=True,
    )


class WindowsPlatform(PlatformAdapter):
    binary_name = "BareBoneVPN.exe"

    def __init__(self):
        self._http_bridge: HttpProxyBridge | None = None

    def start_process(self, args: list[str], log_file):
        return subprocess.Popen(
            args,
            stdout=log_file,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )

    def kill_existing_client(self):
        run_command(
            [
                "taskkill",
                "/F",
                "/IM",
                "BareBoneVPN.exe",
            ],
            timeout=10,
            windows_no_window=True,
        )

    def enable_system_proxy(self, socks_host: str, socks_port: int, network_service: str):
        http_port = int(socks_port) + HTTP_PROXY_PORT_OFFSET

        if self._http_bridge is not None:
            self._http_bridge.stop()

        self._http_bridge = HttpProxyBridge(
            socks_host,
            int(socks_port),
            http_port,
        )

        self._http_bridge.start()

        proxy_server = f"http=127.0.0.1:{http_port};https=127.0.0.1:{http_port}"

        path = r"Software\Microsoft\Windows\CurrentVersion\Internet Settings"

        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, path, 0, winreg.KEY_SET_VALUE) as key:
            winreg.SetValueEx(key, "ProxyEnable", 0, winreg.REG_DWORD, 1)
            winreg.SetValueEx(key, "ProxyServer", 0, winreg.REG_SZ, proxy_server)
            winreg.SetValueEx(
                key,
                "ProxyOverride",
                0,
                winreg.REG_SZ,
                "localhost;127.*;10.*;172.16.*;192.168.*;<local>",
            )

        _refresh_wininet()

    def disable_system_proxy(self, network_service: str):
        if self._http_bridge is not None:
            self._http_bridge.stop()
            self._http_bridge = None

        path = r"Software\Microsoft\Windows\CurrentVersion\Internet Settings"

        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, path, 0, winreg.KEY_SET_VALUE) as key:
            winreg.SetValueEx(key, "ProxyEnable", 0, winreg.REG_DWORD, 0)
            winreg.SetValueEx(key, "ProxyServer", 0, winreg.REG_SZ, "")

        _refresh_wininet()

    def is_port_listening(self, port: int) -> bool:
        code, output = run_command(
            [
                "powershell",
                "-NoProfile",
                "-Command",
                f"Get-NetTCPConnection -LocalPort {int(port)} -State Listen -ErrorAction SilentlyContinue",
            ],
            timeout=3,
            windows_no_window=True,
        )

        return bool(output.strip())


if __name__ == "__main__":
    run_app(WindowsPlatform(), "windows")