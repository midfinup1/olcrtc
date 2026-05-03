import json
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

from PySide6.QtCore import QObject, QThread, Signal
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QFileDialog,
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

DEFAULT_CONTAINER_NAME = "olcrtc-client"
DEFAULT_IMAGE_NAME = "docker.io/library/golang:1.26-alpine"

DEFAULT_SOCKS_HOST = "127.0.0.1"
DEFAULT_SOCKS_PORT = 8808

DEFAULT_CONFIG_URL = "http://194.58.58.92:8090/connection.json"
DEFAULT_CONFIG_TOKEN = "CHANGE_ME_TO_CONNECTION_SERVER_TOKEN"

DEFAULT_DNS_SERVER = "1.1.1.1:53"
DEFAULT_LINK_TYPE = "direct"

DEFAULT_VIDEO_W = "1080"
DEFAULT_VIDEO_H = "1080"
DEFAULT_VIDEO_FPS = "10"
DEFAULT_VIDEO_BITRATE = "1000k"
DEFAULT_VIDEO_CODEC = "tile"
DEFAULT_VIDEO_HW = "none"


def project_root_from_app() -> Path:
    current = Path(__file__).resolve()
    return current.parents[1]


def run_command(args, cwd=None, timeout=None) -> tuple[int, str]:
    try:
        process = subprocess.run(
            args,
            cwd=str(cwd) if cwd else None,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            timeout=timeout,
        )
        return process.returncode, process.stdout
    except subprocess.TimeoutExpired as exc:
        output = exc.stdout or ""
        return 124, output + "\n[timeout]\n"
    except Exception as exc:
        return 1, f"{type(exc).__name__}: {exc}\n"


def fetch_connection_http(url: str, token: str) -> dict:
    if not url.strip():
        raise RuntimeError("Config URL is empty.")

    if not token.strip():
        raise RuntimeError("Config token is empty.")

    request = urllib.request.Request(
        url.strip(),
        headers={
            "Authorization": f"Bearer {token.strip()}",
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
    dns_server = data.get("dns_server", DEFAULT_DNS_SERVER)

    if not provider or not room_id or not encryption_key or not transport_type:
        raise RuntimeError(
            "connection.json is incomplete. Required fields: "
            "provider, room_id, encryption_key, transport_type"
        )

    return {
        "PROVIDER": provider,
        "ROOM_ID": room_id,
        "ENCRYPTION_KEY": encryption_key,
        "TRANSPORT_TYPE": transport_type,
        "DNS_SERVER": dns_server,
        "RAW_JSON": body,
    }


class Worker(QObject):
    finished = Signal(str, bool)

    def __init__(self, title: str, func):
        super().__init__()
        self.title = title
        self.func = func

    def run(self):
        try:
            output = self.func()
            self.finished.emit(output, True)
        except Exception as exc:
            self.finished.emit(f"{self.title} failed:\n{type(exc).__name__}: {exc}", False)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()

        self.setWindowTitle(APP_NAME)
        self.resize(1080, 800)

        self.project_dir = project_root_from_app()

        self.worker_thread = None
        self.worker = None

        self.build_ui()

    def build_ui(self):
        root = QWidget()
        main_layout = QVBoxLayout(root)

        connection_group = QGroupBox("Connection config")
        connection_layout = QFormLayout(connection_group)

        self.project_dir_input = QLineEdit(str(self.project_dir))
        self.project_dir_button = QPushButton("Choose")

        project_dir_row = QHBoxLayout()
        project_dir_row.addWidget(self.project_dir_input)
        project_dir_row.addWidget(self.project_dir_button)

        self.config_url_input = QLineEdit(DEFAULT_CONFIG_URL)
        self.config_token_input = QLineEdit(DEFAULT_CONFIG_TOKEN)
        self.config_token_input.setEchoMode(QLineEdit.Password)

        self.provider_input = QLineEdit("")
        self.room_id_input = QLineEdit("")
        self.key_input = QLineEdit("")
        self.key_input.setEchoMode(QLineEdit.Password)

        self.transport_combo = QComboBox()
        self.transport_combo.addItems(["datachannel", "videochannel", "seichannel"])
        self.transport_combo.setCurrentText("datachannel")

        self.dns_input = QLineEdit(DEFAULT_DNS_SERVER)

        connection_layout.addRow("Local project dir:", project_dir_row)
        connection_layout.addRow("Config URL:", self.config_url_input)
        connection_layout.addRow("Config token:", self.config_token_input)
        connection_layout.addRow("Provider:", self.provider_input)
        connection_layout.addRow("Room ID:", self.room_id_input)
        connection_layout.addRow("Encryption key:", self.key_input)
        connection_layout.addRow("Transport:", self.transport_combo)
        connection_layout.addRow("DNS:", self.dns_input)

        client_group = QGroupBox("Client settings")
        client_layout = QFormLayout(client_group)

        self.socks_host_input = QLineEdit(DEFAULT_SOCKS_HOST)

        self.socks_port_input = QSpinBox()
        self.socks_port_input.setRange(1, 65535)
        self.socks_port_input.setValue(DEFAULT_SOCKS_PORT)

        self.container_name_input = QLineEdit(DEFAULT_CONTAINER_NAME)
        self.image_name_input = QLineEdit(DEFAULT_IMAGE_NAME)

        self.video_w_input = QLineEdit(DEFAULT_VIDEO_W)
        self.video_h_input = QLineEdit(DEFAULT_VIDEO_H)
        self.video_fps_input = QLineEdit(DEFAULT_VIDEO_FPS)
        self.video_bitrate_input = QLineEdit(DEFAULT_VIDEO_BITRATE)
        self.video_codec_input = QLineEdit(DEFAULT_VIDEO_CODEC)
        self.video_hw_input = QLineEdit(DEFAULT_VIDEO_HW)

        client_layout.addRow("SOCKS host:", self.socks_host_input)
        client_layout.addRow("SOCKS port:", self.socks_port_input)
        client_layout.addRow("Container name:", self.container_name_input)
        client_layout.addRow("Image:", self.image_name_input)
        client_layout.addRow("Video width:", self.video_w_input)
        client_layout.addRow("Video height:", self.video_h_input)
        client_layout.addRow("Video fps:", self.video_fps_input)
        client_layout.addRow("Video bitrate:", self.video_bitrate_input)
        client_layout.addRow("Video codec:", self.video_codec_input)
        client_layout.addRow("Video hw:", self.video_hw_input)

        buttons_group = QGroupBox("Actions")
        buttons_layout = QGridLayout(buttons_group)

        self.fetch_button = QPushButton("Fetch config")
        self.start_button = QPushButton("Start client")
        self.stop_button = QPushButton("Stop client")
        self.restart_button = QPushButton("Restart client")

        self.status_button = QPushButton("Status")
        self.logs_button = QPushButton("Refresh logs")
        self.test_ip_button = QPushButton("Test IP")
        self.test_speed_button = QPushButton("Test speed")

        self.enable_proxy_button = QPushButton("Enable macOS SOCKS")
        self.disable_proxy_button = QPushButton("Disable macOS SOCKS")

        self.network_service_input = QLineEdit("Wi-Fi")

        self.auto_fetch_before_start_checkbox = QCheckBox("Fetch config before start")
        self.auto_fetch_before_start_checkbox.setChecked(True)

        buttons_layout.addWidget(self.fetch_button, 0, 0)
        buttons_layout.addWidget(self.start_button, 0, 1)
        buttons_layout.addWidget(self.stop_button, 0, 2)
        buttons_layout.addWidget(self.restart_button, 0, 3)

        buttons_layout.addWidget(self.status_button, 1, 0)
        buttons_layout.addWidget(self.logs_button, 1, 1)
        buttons_layout.addWidget(self.test_ip_button, 1, 2)
        buttons_layout.addWidget(self.test_speed_button, 1, 3)

        buttons_layout.addWidget(QLabel("Network service:"), 2, 0)
        buttons_layout.addWidget(self.network_service_input, 2, 1)
        buttons_layout.addWidget(self.enable_proxy_button, 2, 2)
        buttons_layout.addWidget(self.disable_proxy_button, 2, 3)

        buttons_layout.addWidget(self.auto_fetch_before_start_checkbox, 3, 0, 1, 4)

        self.output = QPlainTextEdit()
        self.output.setReadOnly(True)
        self.output.setLineWrapMode(QPlainTextEdit.NoWrap)

        top_layout = QHBoxLayout()
        top_layout.addWidget(connection_group, 2)
        top_layout.addWidget(client_group, 1)

        main_layout.addLayout(top_layout)
        main_layout.addWidget(buttons_group)
        main_layout.addWidget(QLabel("Output / logs:"))
        main_layout.addWidget(self.output, 1)

        self.setCentralWidget(root)

        self.project_dir_button.clicked.connect(self.choose_project_dir)
        self.fetch_button.clicked.connect(self.fetch_config)
        self.start_button.clicked.connect(self.start_client)
        self.stop_button.clicked.connect(self.stop_client)
        self.restart_button.clicked.connect(self.restart_client)
        self.status_button.clicked.connect(self.show_status)
        self.logs_button.clicked.connect(self.refresh_logs)
        self.test_ip_button.clicked.connect(self.test_ip)
        self.test_speed_button.clicked.connect(self.test_speed)
        self.enable_proxy_button.clicked.connect(self.enable_macos_socks)
        self.disable_proxy_button.clicked.connect(self.disable_macos_socks)

    def append_output(self, text: str):
        self.output.appendPlainText(text.rstrip() + "\n")
        self.output.verticalScrollBar().setValue(self.output.verticalScrollBar().maximum())

    def set_buttons_enabled(self, enabled: bool):
        buttons = [
            self.fetch_button,
            self.start_button,
            self.stop_button,
            self.restart_button,
            self.status_button,
            self.logs_button,
            self.test_ip_button,
            self.test_speed_button,
            self.enable_proxy_button,
            self.disable_proxy_button,
            self.project_dir_button,
        ]

        for button in buttons:
            button.setEnabled(enabled)

    def run_worker(self, title: str, func):
        if self.worker_thread is not None:
            QMessageBox.warning(self, APP_NAME, "Another task is already running.")
            return

        self.set_buttons_enabled(False)
        self.append_output(f"=== {title} ===")

        self.worker_thread = QThread()
        self.worker = Worker(title, func)
        self.worker.moveToThread(self.worker_thread)

        self.worker_thread.started.connect(self.worker.run)
        self.worker.finished.connect(self.on_worker_finished)
        self.worker.finished.connect(self.worker_thread.quit)
        self.worker.finished.connect(self.worker.deleteLater)
        self.worker_thread.finished.connect(self.worker_thread.deleteLater)

        self.worker_thread.start()

    def on_worker_finished(self, output: str, ok: bool):
        self.append_output(output)
        self.append_output("=== done ===" if ok else "=== failed ===")

        self.worker_thread = None
        self.worker = None

        self.set_buttons_enabled(True)

    def choose_project_dir(self):
        chosen = QFileDialog.getExistingDirectory(
            self,
            "Choose olcRTC project directory",
            self.project_dir_input.text(),
        )

        if chosen:
            self.project_dir_input.setText(chosen)

    def get_project_dir(self) -> Path:
        return Path(self.project_dir_input.text()).expanduser().resolve()

    def get_container_name(self) -> str:
        return self.container_name_input.text().strip()

    def get_image_name(self) -> str:
        return self.image_name_input.text().strip()

    def get_socks_host(self) -> str:
        return self.socks_host_input.text().strip()

    def get_socks_port(self) -> int:
        return int(self.socks_port_input.value())

    def fetch_config(self):
        self.run_worker("Fetch config", self.fetch_config_impl)

    def fetch_config_impl(self) -> str:
        url = self.config_url_input.text().strip()
        token = self.config_token_input.text().strip()

        data = fetch_connection_http(url, token)

        provider = data["PROVIDER"]
        room_id = data["ROOM_ID"]
        encryption_key = data["ENCRYPTION_KEY"]
        transport_type = data["TRANSPORT_TYPE"]
        dns_server = data["DNS_SERVER"]

        self.provider_input.setText(provider)
        self.room_id_input.setText(room_id)
        self.key_input.setText(encryption_key)
        self.transport_combo.setCurrentText(transport_type)
        self.dns_input.setText(dns_server)

        return (
            "Loaded config:\n"
            f"Provider: {provider}\n"
            f"Room ID: {room_id}\n"
            f"Transport: {transport_type}\n"
            f"DNS: {dns_server}\n"
        )

    def validate_inputs(self):
        project_dir = self.get_project_dir()

        if not (project_dir / "go.mod").exists():
            raise RuntimeError(f"go.mod not found in {project_dir}")

        if not self.provider_input.text().strip():
            raise RuntimeError("Provider is empty.")

        if not self.room_id_input.text().strip():
            raise RuntimeError("Room ID is empty.")

        if not self.key_input.text().strip():
            raise RuntimeError("Encryption key is empty.")

        if not self.transport_combo.currentText().strip():
            raise RuntimeError("Transport is empty.")

        if not self.dns_input.text().strip():
            raise RuntimeError("DNS is empty.")

    def start_client(self):
        self.run_worker("Start client", self.start_client_impl)

    def start_client_impl(self) -> str:
        output_parts = []

        if self.auto_fetch_before_start_checkbox.isChecked():
            output_parts.append(self.fetch_config_impl())

        self.validate_inputs()

        project_dir = self.get_project_dir()
        container_name = self.get_container_name()
        image_name = self.get_image_name()

        provider = self.provider_input.text().strip()
        room_id = self.room_id_input.text().strip()
        encryption_key = self.key_input.text().strip()
        transport = self.transport_combo.currentText().strip()
        dns_server = self.dns_input.text().strip()

        socks_host = self.get_socks_host()
        socks_port = str(self.get_socks_port())

        output_parts.append("[*] Checking Podman...")
        code, output = run_command(["podman", "info"], timeout=20)
        output_parts.append(output)

        if code != 0:
            raise RuntimeError("Podman is not working. Run: podman machine start")

        output_parts.append("[*] Checking local modules...")

        gr_mod = project_dir / "internal" / "transport" / "videochannel" / "gr" / "go.mod"

        if not gr_mod.exists():
            code, output = run_command(
                ["git", "-C", str(project_dir), "submodule", "update", "--init", "--recursive"],
                timeout=120,
            )
            output_parts.append(output)

            if code != 0:
                raise RuntimeError("Failed to initialize submodules.")

        if not gr_mod.exists():
            raise RuntimeError("Missing internal/transport/videochannel/gr/go.mod")

        output_parts.append("[*] Pulling Go image...")
        code, output = run_command(["podman", "pull", image_name], timeout=180)
        output_parts.append(output)

        if code != 0:
            raise RuntimeError("Failed to pull Go image.")

        output_parts.append("[*] Building olcRTC...")

        code, output = run_command(
            [
                "podman",
                "run",
                "--rm",
                "-v",
                f"{project_dir}:/app",
                "-w",
                "/app",
                image_name,
                "sh",
                "-c",
                "go build -o olcrtc cmd/olcrtc/main.go",
            ],
            cwd=project_dir,
            timeout=300,
        )
        output_parts.append(output)

        if code != 0:
            raise RuntimeError("Build failed.")

        binary_path = project_dir / "olcrtc"

        if not binary_path.exists():
            raise RuntimeError("Build finished, but olcrtc binary was not found.")

        output_parts.append("[*] Stopping old client...")

        run_command(["podman", "stop", container_name], timeout=30)
        run_command(["podman", "rm", container_name], timeout=30)

        olcrtc_args = [
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
            encryption_key,
            "-data",
            "/app/data",
            "-dns",
            dns_server,
        ]

        if transport == "videochannel":
            olcrtc_args.extend(
                [
                    "-video-w",
                    self.video_w_input.text().strip(),
                    "-video-h",
                    self.video_h_input.text().strip(),
                    "-video-fps",
                    self.video_fps_input.text().strip(),
                    "-video-bitrate",
                    self.video_bitrate_input.text().strip(),
                    "-video-codec",
                    self.video_codec_input.text().strip(),
                    "-video-hw",
                    self.video_hw_input.text().strip(),
                ]
            )

        olcrtc_args.extend(
            [
                "-socks-port",
                socks_port,
                "-socks-host",
                "0.0.0.0",
            ]
        )

        output_parts.append("[*] Starting olcRTC client...")

        if transport == "videochannel":
            cmd = [
                "podman",
                "run",
                "-d",
                "--name",
                container_name,
                "--restart",
                "unless-stopped",
                "-p",
                f"{socks_host}:{socks_port}:{socks_port}",
                "-v",
                f"{project_dir}:/app",
                "-w",
                "/app",
                image_name,
                "sh",
                "-c",
                'apk add --no-cache ffmpeg ca-certificates git openssl >/dev/null && ./olcrtc "$@"',
                "--",
                *olcrtc_args,
            ]
        else:
            cmd = [
                "podman",
                "run",
                "-d",
                "--name",
                container_name,
                "--restart",
                "unless-stopped",
                "-p",
                f"{socks_host}:{socks_port}:{socks_port}",
                "-v",
                f"{project_dir}:/app",
                "-w",
                "/app",
                image_name,
                "./olcrtc",
                *olcrtc_args,
            ]

        code, output = run_command(cmd, cwd=project_dir, timeout=120)
        output_parts.append(output)

        if code != 0:
            raise RuntimeError("Failed to start client.")

        output_parts.append(
            "\nClient started:\n"
            f"Provider: {provider}\n"
            f"Room ID: {room_id}\n"
            f"Transport: {transport}\n"
            f"SOCKS5: {socks_host}:{socks_port}\n"
        )

        return "\n".join(output_parts)

    def stop_client(self):
        self.run_worker("Stop client", self.stop_client_impl)

    def stop_client_impl(self) -> str:
        container_name = self.get_container_name()

        code1, out1 = run_command(["podman", "stop", container_name], timeout=30)
        code2, out2 = run_command(["podman", "rm", container_name], timeout=30)

        output = out1 + out2

        if code1 != 0 and "no such container" not in output.lower():
            return output + "\nClient may already be stopped."

        return output + "\nClient stopped."

    def restart_client(self):
        self.run_worker("Restart client", self.restart_client_impl)

    def restart_client_impl(self) -> str:
        stop_output = self.stop_client_impl()
        start_output = self.start_client_impl()

        return stop_output + "\n" + start_output

    def show_status(self):
        self.run_worker("Container status", self.show_status_impl)

    def show_status_impl(self) -> str:
        container_name = self.get_container_name()

        code, output = run_command(
            ["podman", "ps", "-a", "--filter", f"name={container_name}"],
            timeout=20,
        )

        if code != 0:
            raise RuntimeError(output)

        return output

    def refresh_logs(self):
        self.run_worker("Refresh logs", self.refresh_logs_impl)

    def refresh_logs_impl(self) -> str:
        container_name = self.get_container_name()

        code, output = run_command(
            ["podman", "logs", "--tail", "250", container_name],
            timeout=20,
        )

        if code != 0:
            raise RuntimeError(output)

        return output

    def test_ip(self):
        self.run_worker("Test IP", self.test_ip_impl)

    def test_ip_impl(self) -> str:
        socks_host = self.get_socks_host()
        socks_port = str(self.get_socks_port())

        code, output = run_command(
            [
                "curl",
                "--max-time",
                "30",
                "-v",
                "--socks5-hostname",
                f"{socks_host}:{socks_port}",
                "https://ifconfig.me",
            ],
            timeout=40,
        )

        if code != 0:
            raise RuntimeError(output)

        return output

    def test_speed(self):
        self.run_worker("Test speed", self.test_speed_impl)

    def test_speed_impl(self) -> str:
        socks_host = self.get_socks_host()
        socks_port = str(self.get_socks_port())

        code, output = run_command(
            [
                "curl",
                "--socks5-hostname",
                f"{socks_host}:{socks_port}",
                "-o",
                "/dev/null",
                "-w",
                "download: %{speed_download} bytes/sec\n",
                "https://speed.cloudflare.com/__down?bytes=10000000",
            ],
            timeout=180,
        )

        if code != 0:
            raise RuntimeError(output)

        return output

    def enable_macos_socks(self):
        self.run_worker("Enable macOS SOCKS", self.enable_macos_socks_impl)

    def enable_macos_socks_impl(self) -> str:
        service = self.network_service_input.text().strip()
        socks_host = self.get_socks_host()
        socks_port = str(self.get_socks_port())

        if not service:
            raise RuntimeError("Network service is empty.")

        code1, out1 = run_command(
            ["networksetup", "-setsocksfirewallproxy", service, socks_host, socks_port],
            timeout=20,
        )

        code2, out2 = run_command(
            ["networksetup", "-setsocksfirewallproxystate", service, "on"],
            timeout=20,
        )

        code3, out3 = run_command(
            ["networksetup", "-getsocksfirewallproxy", service],
            timeout=20,
        )

        output = out1 + out2 + out3

        if code1 != 0 or code2 != 0:
            raise RuntimeError(output)

        return output + "\nmacOS SOCKS enabled."

    def disable_macos_socks(self):
        self.run_worker("Disable macOS SOCKS", self.disable_macos_socks_impl)

    def disable_macos_socks_impl(self) -> str:
        service = self.network_service_input.text().strip()

        if not service:
            raise RuntimeError("Network service is empty.")

        code, output = run_command(
            ["networksetup", "-setsocksfirewallproxystate", service, "off"],
            timeout=20,
        )

        if code != 0:
            raise RuntimeError(output)

        return output + "\nmacOS SOCKS disabled."


def main():
    app = QApplication(sys.argv)

    window = MainWindow()
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()