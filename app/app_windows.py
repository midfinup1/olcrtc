import json
import os
import signal
import subprocess
import sys
import time
import urllib.error
import urllib.request
import winreg
from pathlib import Path

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QFormLayout,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QPlainTextEdit,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)


APP_NAME = "olcRTC Manager"

DEFAULT_CONFIG_URL = "http://194.58.58.92:8090/connection.json"
DEFAULT_CONFIG_TOKEN = "3311fe77453c1f36d1ad8535470681595c7bf019cf7831a1797e9ce863932973"

DEFAULT_SOCKS_HOST = "127.0.0.1"
DEFAULT_SOCKS_PORT = 8808

DEFAULT_LINK_TYPE = "direct"

DEFAULT_VIDEO_W = "1080"
DEFAULT_VIDEO_H = "1080"
DEFAULT_VIDEO_FPS = "10"
DEFAULT_VIDEO_BITRATE = "1000k"
DEFAULT_VIDEO_CODEC = "tile"
DEFAULT_VIDEO_HW = "none"

CONFIG_REFRESH_INTERVAL_MS = 5 * 60 * 1000


def get_resource_path(name: str) -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys._MEIPASS) / name

    return Path(__file__).resolve().parent / name


def get_data_dir() -> Path:
    data_dir = Path.home() / ".olcrtc-manager" / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    return data_dir


def get_log_path() -> Path:
    log_dir = Path.home() / ".olcrtc-manager" / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    return log_dir / "client.log"


def to_text(value) -> str:
    if value is None:
        return ""

    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")

    return str(value)


def run_command(args, timeout=None) -> tuple[int, str]:
    try:
        process = subprocess.run(
            args,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            timeout=timeout,
            creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
        )

        return process.returncode, to_text(process.stdout)

    except subprocess.TimeoutExpired as exc:
        output = to_text(exc.stdout)
        return 124, output + "\n[timeout]\n"

    except Exception as exc:
        return 1, f"{type(exc).__name__}: {exc}\n"


def fetch_connection_http(url: str, token: str) -> dict:
    url = url.strip()
    token = token.strip()

    if not url:
        raise RuntimeError("Config URL is empty.")

    if not token:
        raise RuntimeError("Config token is empty.")

    request = urllib.request.Request(
        url,
        headers={
            "Authorization": f"Bearer {token}",
            "User-Agent": "olcRTC Manager",
        },
    )

    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            status_code = response.status
            body = response.read().decode("utf-8")

    except urllib.error.HTTPError as exc:
        error_body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP {exc.code}: {error_body}") from exc

    except urllib.error.URLError as exc:
        raise RuntimeError(f"Connection error: {exc}") from exc

    except TimeoutError as exc:
        raise RuntimeError("Connection timeout while fetching config.") from exc

    if status_code != 200:
        raise RuntimeError(f"Unexpected HTTP status: {status_code}")

    try:
        data = json.loads(body)

    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Invalid JSON from server:\n{body}") from exc

    provider = data.get("provider", "")
    room_id = data.get("room_id", "")
    encryption_key = data.get("encryption_key", "")
    transport_type = data.get("transport_type", "")
    dns_server = data.get("dns_server", "1.1.1.1:53")

    if not provider or not room_id or not encryption_key or not transport_type:
        raise RuntimeError(
            "connection.json is incomplete. Required fields: "
            "provider, room_id, encryption_key, transport_type"
        )

    return {
        "provider": provider,
        "room_id": room_id,
        "encryption_key": encryption_key,
        "transport_type": transport_type,
        "dns_server": dns_server,
        "raw_json": body,
    }


def set_windows_proxy_enabled(enabled: bool, socks_host: str, socks_port: int):
    proxy_server = f"socks={socks_host}:{socks_port}"

    path = r"Software\Microsoft\Windows\CurrentVersion\Internet Settings"

    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, path, 0, winreg.KEY_SET_VALUE) as key:
        winreg.SetValueEx(key, "ProxyEnable", 0, winreg.REG_DWORD, 1 if enabled else 0)

        if enabled:
            winreg.SetValueEx(key, "ProxyServer", 0, winreg.REG_SZ, proxy_server)

    run_command(
        [
            "powershell",
            "-NoProfile",
            "-Command",
            "$signature='[DllImport(\"wininet.dll\", SetLastError = true)] public static extern bool InternetSetOption(IntPtr hInternet, int dwOption, IntPtr lpBuffer, int dwBufferLength);';"
            "$type=Add-Type -MemberDefinition $signature -Name WinInet -Namespace Native -PassThru;"
            "$type::InternetSetOption([IntPtr]::Zero, 39, [IntPtr]::Zero, 0) | Out-Null;"
            "$type::InternetSetOption([IntPtr]::Zero, 37, [IntPtr]::Zero, 0) | Out-Null;"
        ],
        timeout=10,
    )


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()

        self.setWindowTitle(APP_NAME)
        self.resize(980, 780)

        self.client_process: subprocess.Popen | None = None

        self.client_log_file = None
        self.client_log_path = get_log_path()
        self.client_log_position = 0

        self.is_reconnecting = False

        self.log_timer = QTimer(self)
        self.log_timer.setInterval(500)
        self.log_timer.timeout.connect(self.read_client_logs)

        self.config_timer = QTimer(self)
        self.config_timer.setInterval(CONFIG_REFRESH_INTERVAL_MS)
        self.config_timer.timeout.connect(self.check_config_update)

        self.build_ui()

    def build_ui(self):
        root = QWidget()
        main_layout = QVBoxLayout(root)

        config_group = QGroupBox("Server config")
        config_layout = QFormLayout(config_group)

        self.config_url_input = QLineEdit(DEFAULT_CONFIG_URL)

        self.config_token_input = QLineEdit(DEFAULT_CONFIG_TOKEN)
        self.config_token_input.setEchoMode(QLineEdit.Password)

        self.provider_input = QLineEdit("")
        self.room_id_input = QLineEdit("")

        self.key_input = QLineEdit("")
        self.key_input.setEchoMode(QLineEdit.Password)

        self.transport_input = QLineEdit("")
        self.dns_input = QLineEdit("")

        config_layout.addRow("Config URL:", self.config_url_input)
        config_layout.addRow("Config token:", self.config_token_input)
        config_layout.addRow("Provider:", self.provider_input)
        config_layout.addRow("Room ID:", self.room_id_input)
        config_layout.addRow("Encryption key:", self.key_input)
        config_layout.addRow("Transport:", self.transport_input)
        config_layout.addRow("DNS:", self.dns_input)

        client_group = QGroupBox("Client settings")
        client_layout = QFormLayout(client_group)

        self.socks_host_input = QLineEdit(DEFAULT_SOCKS_HOST)

        self.socks_port_input = QSpinBox()
        self.socks_port_input.setRange(1, 65535)
        self.socks_port_input.setValue(DEFAULT_SOCKS_PORT)

        self.auto_fetch_checkbox = QCheckBox("Fetch config before connect")
        self.auto_fetch_checkbox.setChecked(True)

        self.auto_enable_proxy_checkbox = QCheckBox("Enable Windows proxy after connect")
        self.auto_enable_proxy_checkbox.setChecked(True)

        self.auto_disable_proxy_checkbox = QCheckBox("Disable Windows proxy on disconnect")
        self.auto_disable_proxy_checkbox.setChecked(True)

        self.auto_refresh_config_checkbox = QCheckBox("Auto refresh config every 5 minutes")
        self.auto_refresh_config_checkbox.setChecked(True)

        client_layout.addRow("SOCKS host:", self.socks_host_input)
        client_layout.addRow("SOCKS port:", self.socks_port_input)
        client_layout.addRow("", self.auto_fetch_checkbox)
        client_layout.addRow("", self.auto_enable_proxy_checkbox)
        client_layout.addRow("", self.auto_disable_proxy_checkbox)
        client_layout.addRow("", self.auto_refresh_config_checkbox)

        buttons_group = QGroupBox("Actions")
        buttons_layout = QGridLayout(buttons_group)

        self.fetch_button = QPushButton("Fetch config")
        self.connect_button = QPushButton("Connect")
        self.disconnect_button = QPushButton("Disconnect")
        self.check_config_button = QPushButton("Check config now")
        self.test_ip_button = QPushButton("Test IP")
        self.test_speed_button = QPushButton("Test speed")
        self.enable_proxy_button = QPushButton("Enable Windows proxy")
        self.disable_proxy_button = QPushButton("Disable Windows proxy")
        self.clear_logs_button = QPushButton("Clear logs")

        buttons_layout.addWidget(self.fetch_button, 0, 0)
        buttons_layout.addWidget(self.connect_button, 0, 1)
        buttons_layout.addWidget(self.disconnect_button, 0, 2)
        buttons_layout.addWidget(self.check_config_button, 0, 3)

        buttons_layout.addWidget(self.test_ip_button, 1, 0)
        buttons_layout.addWidget(self.test_speed_button, 1, 1)
        buttons_layout.addWidget(self.enable_proxy_button, 1, 2)
        buttons_layout.addWidget(self.disable_proxy_button, 1, 3)

        buttons_layout.addWidget(self.clear_logs_button, 2, 0, 1, 4)

        status_group = QGroupBox("Status")
        status_layout = QFormLayout(status_group)

        self.status_label = QLabel("Disconnected")
        self.socks_label = QLabel(f"{DEFAULT_SOCKS_HOST}:{DEFAULT_SOCKS_PORT}")
        self.refresh_label = QLabel("Auto-refresh stopped")

        status_layout.addRow("Client:", self.status_label)
        status_layout.addRow("SOCKS5:", self.socks_label)
        status_layout.addRow("Config refresh:", self.refresh_label)

        self.output = QPlainTextEdit()
        self.output.setReadOnly(True)
        self.output.setLineWrapMode(QPlainTextEdit.NoWrap)

        top_layout = QHBoxLayout()
        top_layout.addWidget(config_group, 2)
        top_layout.addWidget(client_group, 1)

        main_layout.addLayout(top_layout)
        main_layout.addWidget(buttons_group)
        main_layout.addWidget(status_group)
        main_layout.addWidget(QLabel("Logs:"))
        main_layout.addWidget(self.output, 1)

        self.setCentralWidget(root)

        self.fetch_button.clicked.connect(self.fetch_config)
        self.connect_button.clicked.connect(self.connect_client)
        self.disconnect_button.clicked.connect(self.disconnect_client)
        self.check_config_button.clicked.connect(self.check_config_update)
        self.test_ip_button.clicked.connect(self.test_ip)
        self.test_speed_button.clicked.connect(self.test_speed)
        self.enable_proxy_button.clicked.connect(self.enable_windows_proxy)
        self.disable_proxy_button.clicked.connect(self.disable_windows_proxy)
        self.clear_logs_button.clicked.connect(self.clear_logs)

        self.update_buttons()

    def append_log(self, text: str):
        if text is None:
            return

        text = str(text)

        if not text:
            return

        self.output.appendPlainText(text.rstrip() + "\n")
        self.output.verticalScrollBar().setValue(self.output.verticalScrollBar().maximum())

    def clear_logs(self):
        self.output.clear()

        try:
            self.client_log_path.unlink(missing_ok=True)
        except Exception:
            pass

        self.client_log_position = 0

    def get_socks_host(self) -> str:
        return self.socks_host_input.text().strip()

    def get_socks_port(self) -> int:
        return int(self.socks_port_input.value())

    def update_buttons(self):
        running = self.client_process is not None and self.client_process.poll() is None

        self.connect_button.setEnabled(not running and not self.is_reconnecting)
        self.disconnect_button.setEnabled(running or self.is_reconnecting)

        self.status_label.setText("Connected" if running else "Disconnected")
        self.socks_label.setText(f"{self.get_socks_host()}:{self.get_socks_port()}")

        if self.config_timer.isActive():
            self.refresh_label.setText("Auto-refresh active, every 5 minutes")
        else:
            self.refresh_label.setText("Auto-refresh stopped")

    def apply_config_data(self, data: dict):
        self.provider_input.setText(data["provider"])
        self.room_id_input.setText(data["room_id"])
        self.key_input.setText(data["encryption_key"])
        self.transport_input.setText(data["transport_type"])
        self.dns_input.setText(data["dns_server"])

    def fetch_config(self):
        try:
            self.append_log("=== Fetch config ===")

            data = fetch_connection_http(
                self.config_url_input.text(),
                self.config_token_input.text(),
            )

            self.apply_config_data(data)

            self.append_log(
                "Loaded config:\n"
                f"Provider: {data['provider']}\n"
                f"Room ID: {data['room_id']}\n"
                f"Transport: {data['transport_type']}\n"
                f"DNS: {data['dns_server']}\n"
            )

            self.append_log("=== done ===")

        except Exception as exc:
            self.append_log(f"Fetch config failed:\n{type(exc).__name__}: {exc}")
            self.append_log("=== failed ===")

    def validate_connection_fields(self):
        if not self.provider_input.text().strip():
            raise RuntimeError("Provider is empty.")

        if not self.room_id_input.text().strip():
            raise RuntimeError("Room ID is empty.")

        if not self.key_input.text().strip():
            raise RuntimeError("Encryption key is empty.")

        if not self.transport_input.text().strip():
            raise RuntimeError("Transport is empty.")

        if not self.dns_input.text().strip():
            raise RuntimeError("DNS is empty.")

    def build_olcrtc_args(self) -> list[str]:
        olcrtc_binary = get_resource_path("olcrtc.exe")

        if not olcrtc_binary.exists():
            raise RuntimeError(f"olcrtc.exe binary not found: {olcrtc_binary}")

        provider = self.provider_input.text().strip()
        room_id = self.room_id_input.text().strip()
        key = self.key_input.text().strip()
        transport = self.transport_input.text().strip()
        dns = self.dns_input.text().strip()

        data_dir = get_data_dir()

        args = [
            str(olcrtc_binary),
            "-mode",
            "cnc",
            "-link",
            DEFAULT_LINK_TYPE,
            "-transport",
            transport,
            "-provider",
            provider,
            "-id",
            room_id,
            "-key",
            key,
            "-data",
            str(data_dir),
            "-dns",
            dns,
            "-socks-host",
            self.get_socks_host(),
            "-socks-port",
            str(self.get_socks_port()),
        ]

        if transport == "videochannel":
            args.extend(
                [
                    "-video-w",
                    DEFAULT_VIDEO_W,
                    "-video-h",
                    DEFAULT_VIDEO_H,
                    "-video-fps",
                    DEFAULT_VIDEO_FPS,
                    "-video-bitrate",
                    DEFAULT_VIDEO_BITRATE,
                    "-video-codec",
                    DEFAULT_VIDEO_CODEC,
                    "-video-hw",
                    DEFAULT_VIDEO_HW,
                ]
            )

        return args

    def kill_existing_olcrtc(self):
        run_command(["taskkill", "/F", "/IM", "olcrtc.exe"], timeout=10)

    def wait_socks_port_free(self, timeout_seconds: int = 5) -> bool:
        deadline = time.time() + timeout_seconds
        port = str(self.get_socks_port())

        while time.time() < deadline:
            code, output = run_command(
                [
                    "powershell",
                    "-NoProfile",
                    "-Command",
                    f"Get-NetTCPConnection -LocalPort {port} -State Listen -ErrorAction SilentlyContinue",
                ],
                timeout=3,
            )

            if not output.strip():
                return True

            time.sleep(0.3)

        return False

    def cleanup_old_client(self):
        self.append_log("[*] Cleaning old client state...")

        self.disable_windows_proxy_silent()

        if self.client_process is not None and self.client_process.poll() is None:
            try:
                self.client_process.terminate()
                self.client_process.wait(timeout=3)
            except Exception:
                try:
                    self.client_process.kill()
                    self.client_process.wait(timeout=3)
                except Exception:
                    pass

        self.client_process = None

        if self.client_log_file is not None:
            try:
                self.client_log_file.close()
            except Exception:
                pass

        self.client_log_file = None

        self.kill_existing_olcrtc()

        if self.wait_socks_port_free(timeout_seconds=5):
            self.append_log("[+] SOCKS port is free.")
        else:
            self.append_log("[!] SOCKS port may still be busy.")

    def start_config_refresh_if_needed(self):
        if self.auto_refresh_config_checkbox.isChecked():
            self.config_timer.start()
        else:
            self.config_timer.stop()

        self.update_buttons()

    def stop_config_refresh(self):
        self.config_timer.stop()
        self.update_buttons()

    def connect_client(self):
        try:
            self.append_log("=== Connect ===")

            if self.client_process is not None and self.client_process.poll() is None:
                self.append_log("Client is already running.")
                self.update_buttons()
                return

            self.cleanup_old_client()

            if self.auto_fetch_checkbox.isChecked():
                data = fetch_connection_http(
                    self.config_url_input.text(),
                    self.config_token_input.text(),
                )

                self.apply_config_data(data)

                self.append_log(
                    "Config loaded:\n"
                    f"Provider: {data['provider']}\n"
                    f"Room ID: {data['room_id']}\n"
                    f"Transport: {data['transport_type']}\n"
                )

            self.validate_connection_fields()

            args = self.build_olcrtc_args()

            self.client_log_path.parent.mkdir(parents=True, exist_ok=True)
            self.client_log_file = open(self.client_log_path, "a", encoding="utf-8", buffering=1)
            self.client_log_position = self.client_log_path.stat().st_size if self.client_log_path.exists() else 0

            self.append_log("Starting olcRTC client...")
            self.append_log("Command:")
            self.append_log(str(args[0]) + " ...")

            self.client_process = subprocess.Popen(
                args,
                stdout=self.client_log_file,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
                creationflags=subprocess.CREATE_NO_WINDOW,
            )

            self.log_timer.start()

            self.append_log(
                "Client started.\n"
                f"SOCKS5: {self.get_socks_host()}:{self.get_socks_port()}"
            )

            time.sleep(1)

            if self.auto_enable_proxy_checkbox.isChecked():
                self.enable_windows_proxy()

            self.start_config_refresh_if_needed()

            self.update_buttons()
            self.append_log("=== done ===")

        except Exception as exc:
            self.append_log(f"Connect failed:\n{type(exc).__name__}: {exc}")
            self.append_log("=== failed ===")
            self.update_buttons()

    def read_client_logs(self):
        try:
            if self.client_log_path.exists():
                with open(self.client_log_path, "r", encoding="utf-8", errors="replace") as f:
                    f.seek(self.client_log_position)
                    new_data = f.read()
                    self.client_log_position = f.tell()

                if new_data:
                    self.append_log(new_data.rstrip())

        except Exception as exc:
            self.append_log(f"Log read error: {type(exc).__name__}: {exc}")

        if self.client_process is None:
            self.log_timer.stop()
            self.update_buttons()
            return

        if self.client_process.poll() is not None:
            self.log_timer.stop()
            self.append_log(f"Client exited with code {self.client_process.returncode}")

            if self.client_log_file is not None:
                try:
                    self.client_log_file.close()
                except Exception:
                    pass

            self.client_log_file = None
            self.client_process = None
            self.stop_config_refresh()
            self.update_buttons()

    def disconnect_client(self):
        try:
            self.append_log("=== Disconnect ===")

            self.stop_config_refresh()

            if self.client_process is not None and self.client_process.poll() is None:
                try:
                    self.client_process.terminate()
                    self.client_process.wait(timeout=5)
                except Exception:
                    try:
                        self.client_process.kill()
                        self.client_process.wait(timeout=5)
                    except Exception:
                        pass

                self.append_log("Client process stopped.")
            else:
                self.append_log("Client is not running.")

            self.kill_existing_olcrtc()

            self.client_process = None
            self.log_timer.stop()

            if self.client_log_file is not None:
                try:
                    self.client_log_file.close()
                except Exception:
                    pass

            self.client_log_file = None

            if self.auto_disable_proxy_checkbox.isChecked():
                self.disable_windows_proxy()

            self.wait_socks_port_free(timeout_seconds=5)

            self.update_buttons()
            self.append_log("=== done ===")

        except Exception as exc:
            self.append_log(f"Disconnect failed:\n{type(exc).__name__}: {exc}")
            self.append_log("=== failed ===")
            self.update_buttons()

    def check_config_update(self):
        try:
            self.append_log("=== Auto config check ===")

            running = self.client_process is not None and self.client_process.poll() is None

            data = fetch_connection_http(
                self.config_url_input.text(),
                self.config_token_input.text(),
            )

            old_provider = self.provider_input.text().strip()
            old_room_id = self.room_id_input.text().strip()
            old_key = self.key_input.text().strip()
            old_transport = self.transport_input.text().strip()
            old_dns = self.dns_input.text().strip()

            new_provider = data["provider"]
            new_room_id = data["room_id"]
            new_key = data["encryption_key"]
            new_transport = data["transport_type"]
            new_dns = data["dns_server"]

            unchanged = (
                old_provider == new_provider
                and old_room_id == new_room_id
                and old_key == new_key
                and old_transport == new_transport
                and old_dns == new_dns
            )

            if unchanged:
                self.append_log("[auto-refresh] Config is unchanged.")
                self.append_log("=== done ===")
                return

            self.append_log("[auto-refresh] Config changed.")
            self.append_log(f"Old provider:  {old_provider}")
            self.append_log(f"New provider:  {new_provider}")
            self.append_log(f"Old room:      {old_room_id}")
            self.append_log(f"New room:      {new_room_id}")
            self.append_log(f"Old transport: {old_transport}")
            self.append_log(f"New transport: {new_transport}")

            self.apply_config_data(data)

            if not running:
                self.append_log("[auto-refresh] Client is not running. Config updated only.")
                self.append_log("=== done ===")
                return

            self.append_log("[auto-refresh] Reconnecting client...")

            self.is_reconnecting = True
            self.update_buttons()

            was_auto_disable = self.auto_disable_proxy_checkbox.isChecked()
            self.auto_disable_proxy_checkbox.setChecked(False)

            try:
                self.disconnect_client()
            finally:
                self.auto_disable_proxy_checkbox.setChecked(was_auto_disable)

            self.connect_client()

            self.is_reconnecting = False
            self.update_buttons()

            self.append_log("=== done ===")

        except Exception as exc:
            self.is_reconnecting = False
            self.update_buttons()
            self.append_log(f"[auto-refresh] Failed:\n{type(exc).__name__}: {exc}")
            self.append_log("=== failed ===")

    def test_ip(self):
        try:
            self.append_log("=== Test IP ===")

            code, output = run_command(
                [
                    "curl",
                    "--max-time",
                    "30",
                    "-v",
                    "--socks5-hostname",
                    f"{self.get_socks_host()}:{self.get_socks_port()}",
                    "https://ifconfig.me",
                ],
                timeout=40,
            )

            self.append_log(output)

            if code != 0:
                raise RuntimeError(f"curl failed with code {code}")

            self.append_log("=== done ===")

        except Exception as exc:
            self.append_log(f"Test IP failed:\n{type(exc).__name__}: {exc}")
            self.append_log("=== failed ===")

    def test_speed(self):
        try:
            self.append_log("=== Test speed ===")

            code, output = run_command(
                [
                    "curl",
                    "--socks5-hostname",
                    f"{self.get_socks_host()}:{self.get_socks_port()}",
                    "-o",
                    "NUL",
                    "-w",
                    "download: %{speed_download} bytes/sec\n",
                    "https://speed.cloudflare.com/__down?bytes=10000000",
                ],
                timeout=180,
            )

            self.append_log(output)

            if code != 0:
                raise RuntimeError(f"curl failed with code {code}")

            self.append_log("=== done ===")

        except Exception as exc:
            self.append_log(f"Test speed failed:\n{type(exc).__name__}: {exc}")
            self.append_log("=== failed ===")

    def enable_windows_proxy(self):
        try:
            socks_host = self.get_socks_host()
            socks_port = self.get_socks_port()

            set_windows_proxy_enabled(True, socks_host, socks_port)

            self.append_log(f"Windows proxy enabled: socks={socks_host}:{socks_port}")

        except Exception as exc:
            self.append_log(f"Enable Windows proxy failed:\n{type(exc).__name__}: {exc}")

    def disable_windows_proxy(self):
        try:
            set_windows_proxy_enabled(False, self.get_socks_host(), self.get_socks_port())

            self.append_log("Windows proxy disabled.")

        except Exception as exc:
            self.append_log(f"Disable Windows proxy failed:\n{type(exc).__name__}: {exc}")

    def disable_windows_proxy_silent(self):
        try:
            set_windows_proxy_enabled(False, self.get_socks_host(), self.get_socks_port())
        except Exception:
            pass

    def closeEvent(self, event):
        if self.client_process is not None and self.client_process.poll() is None:
            reply = QMessageBox.question(
                self,
                APP_NAME,
                "Client is still running. Stop it and quit?",
                QMessageBox.Yes | QMessageBox.No,
            )

            if reply == QMessageBox.Yes:
                self.disconnect_client()
                event.accept()
            else:
                event.ignore()
        else:
            self.stop_config_refresh()
            event.accept()


def main():
    app = QApplication(sys.argv)

    window = MainWindow()
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()