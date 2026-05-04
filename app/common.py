import json
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QDialog,
    QFormLayout,
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

CONFIG_REFRESH_INTERVAL_MS = 5 * 60 * 1000
LOG_READ_INTERVAL_MS = 500

DEFAULT_CONFIG_URL = "http://194.58.58.92:8090/connection.json"
DEFAULT_CONFIG_TOKEN = "3311fe77453c1f36d1ad8535470681595c7bf019cf7831a1797e9ce863932973"

DEFAULT_SOCKS_HOST = "127.0.0.1"
DEFAULT_SOCKS_PORT = 8808

DEFAULT_DNS_SERVER = "1.1.1.1:53"
DEFAULT_LINK_TYPE = "direct"
DEFAULT_TRANSPORT = "datachannel"

DEFAULT_NETWORK_SERVICE = "Wi-Fi"


def to_text(value) -> str:
    if value is None:
        return ""

    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")

    return str(value)


def get_user_dir() -> Path:
    path = Path.home() / ".olcrtc-manager"
    path.mkdir(parents=True, exist_ok=True)
    return path


def get_data_dir() -> Path:
    path = get_user_dir() / "data"
    path.mkdir(parents=True, exist_ok=True)
    return path


def get_log_path() -> Path:
    path = get_user_dir() / "logs"
    path.mkdir(parents=True, exist_ok=True)
    return path / "client.log"


def get_settings_path() -> Path:
    return get_user_dir() / "settings.json"


def run_command(args, timeout=None, windows_no_window=False) -> tuple[int, str]:
    creationflags = 0

    if sys.platform == "win32" and windows_no_window:
        creationflags = subprocess.CREATE_NO_WINDOW

    try:
        process = subprocess.run(
            args,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            timeout=timeout,
            creationflags=creationflags,
        )

        return process.returncode, to_text(process.stdout)

    except subprocess.TimeoutExpired as exc:
        return 124, to_text(exc.stdout) + "\n[timeout]\n"

    except Exception as exc:
        return 1, f"{type(exc).__name__}: {exc}\n"


def fetch_connection_http(url: str, token: str) -> dict:
    url = url.strip()
    token = token.strip()

    if not url:
        raise RuntimeError("Config URL is empty. Open Settings and enter Config URL.")

    if not token:
        raise RuntimeError("Config token is empty. Open Settings and enter token.")

    request = urllib.request.Request(
        url,
        headers={
            "Authorization": f"Bearer {token}",
            "User-Agent": APP_NAME,
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
    dns_server = data.get("dns_server", DEFAULT_DNS_SERVER)

    if not provider or not room_id or not encryption_key:
        raise RuntimeError(
            "connection.json is incomplete. Required fields: "
            "provider, room_id, encryption_key"
        )

    return {
        "provider": provider,
        "room_id": room_id,
        "encryption_key": encryption_key,
        "dns_server": dns_server,
    }


class PlatformAdapter:
    binary_name = "olcrtc"

    def resource_path(self, name: str) -> Path:
        if getattr(sys, "frozen", False):
            return Path(sys._MEIPASS) / name

        return Path(__file__).resolve().parent / name

    def binary_path(self) -> Path:
        return self.resource_path(self.binary_name)

    def start_process(self, args: list[str], log_file):
        return subprocess.Popen(
            args,
            stdout=log_file,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )

    def kill_existing_client(self):
        raise NotImplementedError

    def enable_system_proxy(self, socks_host: str, socks_port: int, network_service: str):
        raise NotImplementedError

    def disable_system_proxy(self, network_service: str):
        raise NotImplementedError

    def is_port_listening(self, port: int) -> bool:
        raise NotImplementedError


class SettingsDialog(QDialog):
    def __init__(self, parent, settings: dict, platform_name: str):
        super().__init__(parent)

        self.setWindowTitle("Settings")
        self.resize(520, 260)

        self.config_url_input = QLineEdit(settings.get("config_url", DEFAULT_CONFIG_URL))
        self.config_token_input = QLineEdit(settings.get("config_token", DEFAULT_CONFIG_TOKEN))
        self.config_token_input.setEchoMode(QLineEdit.Password)

        self.socks_host_input = QLineEdit(settings.get("socks_host", DEFAULT_SOCKS_HOST))

        self.socks_port_input = QSpinBox()
        self.socks_port_input.setRange(1, 65535)
        self.socks_port_input.setValue(int(settings.get("socks_port", DEFAULT_SOCKS_PORT)))

        self.network_service_input = QLineEdit(settings.get("network_service", DEFAULT_NETWORK_SERVICE))

        self.auto_connect_checkbox = QCheckBox("Auto connect on app start")
        self.auto_connect_checkbox.setChecked(bool(settings.get("auto_connect", False)))

        self.auto_refresh_checkbox = QCheckBox("Auto refresh room every 5 minutes")
        self.auto_refresh_checkbox.setChecked(bool(settings.get("auto_refresh", True)))

        form = QFormLayout()
        form.addRow("Config URL:", self.config_url_input)
        form.addRow("Config token:", self.config_token_input)
        form.addRow("SOCKS host:", self.socks_host_input)
        form.addRow("SOCKS port:", self.socks_port_input)

        if platform_name == "macos":
            form.addRow("Network service:", self.network_service_input)

        form.addRow("", self.auto_connect_checkbox)
        form.addRow("", self.auto_refresh_checkbox)

        save_button = QPushButton("Save")
        cancel_button = QPushButton("Cancel")

        save_button.clicked.connect(self.accept)
        cancel_button.clicked.connect(self.reject)

        buttons = QHBoxLayout()
        buttons.addStretch()
        buttons.addWidget(cancel_button)
        buttons.addWidget(save_button)

        layout = QVBoxLayout()
        layout.addLayout(form)
        layout.addLayout(buttons)

        self.setLayout(layout)

    def values(self) -> dict:
        return {
            "config_url": self.config_url_input.text().strip() or DEFAULT_CONFIG_URL,
            "config_token": self.config_token_input.text().strip() or DEFAULT_CONFIG_TOKEN,
            "socks_host": self.socks_host_input.text().strip() or DEFAULT_SOCKS_HOST,
            "socks_port": int(self.socks_port_input.value()),
            "network_service": self.network_service_input.text().strip() or DEFAULT_NETWORK_SERVICE,
            "auto_connect": self.auto_connect_checkbox.isChecked(),
            "auto_refresh": self.auto_refresh_checkbox.isChecked(),
        }


class MainWindow(QMainWindow):
    def __init__(self, platform: PlatformAdapter, platform_name: str):
        super().__init__()

        self.platform = platform
        self.platform_name = platform_name

        self.setWindowTitle(APP_NAME)
        self.resize(760, 560)

        self.client_process = None
        self.client_log_file = None
        self.client_log_path = get_log_path()
        self.client_log_position = 0

        self.current_config = None
        self.is_reconnecting = False

        self.settings = self.load_settings()

        self.log_timer = QTimer(self)
        self.log_timer.setInterval(LOG_READ_INTERVAL_MS)
        self.log_timer.timeout.connect(self.read_client_logs)

        self.config_timer = QTimer(self)
        self.config_timer.setInterval(CONFIG_REFRESH_INTERVAL_MS)
        self.config_timer.timeout.connect(self.check_config_update)

        self.build_ui()

        if self.settings.get("auto_connect", False):
            QTimer.singleShot(500, self.connect_client)

    def build_ui(self):
        root = QWidget()
        layout = QVBoxLayout(root)

        self.status_label = QLabel("Выключено")
        self.status_label.setStyleSheet("font-size: 22px; font-weight: 600;")

        self.details_label = QLabel("SOCKS5: 127.0.0.1:8808")
        self.details_label.setStyleSheet("font-size: 13px; color: #666;")

        self.connect_button = QPushButton("Включить")
        self.disconnect_button = QPushButton("Выключить")
        self.test_ip_button = QPushButton("Проверить IP")
        self.logs_button = QPushButton("Показать логи")
        self.settings_button = QPushButton("Настройки")

        self.connect_button.setMinimumHeight(42)
        self.disconnect_button.setMinimumHeight(42)
        self.test_ip_button.setMinimumHeight(36)
        self.logs_button.setMinimumHeight(36)
        self.settings_button.setMinimumHeight(36)

        top_buttons = QHBoxLayout()
        top_buttons.addWidget(self.connect_button)
        top_buttons.addWidget(self.disconnect_button)

        second_buttons = QHBoxLayout()
        second_buttons.addWidget(self.test_ip_button)
        second_buttons.addWidget(self.logs_button)
        second_buttons.addWidget(self.settings_button)

        self.output = QPlainTextEdit()
        self.output.setReadOnly(True)
        self.output.setLineWrapMode(QPlainTextEdit.NoWrap)
        self.output.hide()

        layout.addWidget(self.status_label)
        layout.addWidget(self.details_label)
        layout.addSpacing(10)
        layout.addLayout(top_buttons)
        layout.addLayout(second_buttons)
        layout.addWidget(self.output, 1)

        self.setCentralWidget(root)

        self.connect_button.clicked.connect(self.connect_client)
        self.disconnect_button.clicked.connect(self.disconnect_client)
        self.test_ip_button.clicked.connect(self.test_ip)
        self.logs_button.clicked.connect(self.toggle_logs)
        self.settings_button.clicked.connect(self.open_settings)

        self.update_state()

    def load_settings(self) -> dict:
        path = get_settings_path()

        defaults = {
            "config_url": DEFAULT_CONFIG_URL,
            "config_token": DEFAULT_CONFIG_TOKEN,
            "socks_host": DEFAULT_SOCKS_HOST,
            "socks_port": DEFAULT_SOCKS_PORT,
            "network_service": DEFAULT_NETWORK_SERVICE,
            "auto_connect": False,
            "auto_refresh": True,
        }

        if not path.exists():
            return defaults

        try:
            data = json.loads(path.read_text(encoding="utf-8"))

            if not data.get("config_url"):
                data["config_url"] = DEFAULT_CONFIG_URL

            if not data.get("config_token"):
                data["config_token"] = DEFAULT_CONFIG_TOKEN

            defaults.update(data)
            return defaults

        except Exception:
            return defaults

    def save_settings(self):
        get_settings_path().write_text(
            json.dumps(self.settings, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def append_log(self, text: str):
        if text is None:
            return

        text = str(text).rstrip()

        if not text:
            return

        self.output.appendPlainText(text)
        self.output.verticalScrollBar().setValue(self.output.verticalScrollBar().maximum())

    def set_status(self, text: str):
        self.status_label.setText(text)

    def socks_host(self) -> str:
        return self.settings.get("socks_host", DEFAULT_SOCKS_HOST)

    def socks_port(self) -> int:
        return int(self.settings.get("socks_port", DEFAULT_SOCKS_PORT))

    def network_service(self) -> str:
        return self.settings.get("network_service", DEFAULT_NETWORK_SERVICE)

    def is_running(self) -> bool:
        return self.client_process is not None and self.client_process.poll() is None

    def update_state(self):
        running = self.is_running()

        if running:
            self.set_status("Включено")
        elif self.is_reconnecting:
            self.set_status("Переподключение...")
        else:
            self.set_status("Выключено")

        self.details_label.setText(f"SOCKS5: {self.socks_host()}:{self.socks_port()}")

        self.connect_button.setEnabled(not running and not self.is_reconnecting)
        self.disconnect_button.setEnabled(running or self.is_reconnecting)

    def toggle_logs(self):
        if self.output.isVisible():
            self.output.hide()
            self.logs_button.setText("Показать логи")
        else:
            self.output.show()
            self.logs_button.setText("Скрыть логи")

    def open_settings(self):
        dialog = SettingsDialog(self, self.settings, self.platform_name)

        if dialog.exec() == QDialog.Accepted:
            self.settings = dialog.values()
            self.save_settings()
            self.update_state()
            self.append_log("Настройки сохранены.")

    def fetch_config(self) -> dict:
        return fetch_connection_http(
            self.settings.get("config_url", DEFAULT_CONFIG_URL),
            self.settings.get("config_token", DEFAULT_CONFIG_TOKEN),
        )

    def cleanup_old_client(self):
        self.append_log("Очистка старого состояния...")

        try:
            self.platform.disable_system_proxy(self.network_service())
        except Exception:
            pass

        if self.is_running():
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

        try:
            self.platform.kill_existing_client()
        except Exception:
            pass

        self.wait_port_free()

    def wait_port_free(self, timeout_seconds: int = 5) -> bool:
        deadline = time.time() + timeout_seconds

        while time.time() < deadline:
            if not self.platform.is_port_listening(self.socks_port()):
                return True

            time.sleep(0.3)

        return False

    def build_client_args(self, cfg: dict) -> list[str]:
        binary = self.platform.binary_path()

        if not binary.exists():
            raise RuntimeError(f"olcRTC binary not found: {binary}")

        if sys.platform != "win32":
            binary.chmod(0o755)

        return [
            str(binary),
            "-mode",
            "cnc",
            "-link",
            DEFAULT_LINK_TYPE,
            "-transport",
            DEFAULT_TRANSPORT,
            "-provider",
            cfg["provider"],
            "-id",
            cfg["room_id"],
            "-key",
            cfg["encryption_key"],
            "-data",
            str(get_data_dir()),
            "-dns",
            cfg.get("dns_server", DEFAULT_DNS_SERVER),
            "-socks-host",
            self.socks_host(),
            "-socks-port",
            str(self.socks_port()),
        ]

    def wait_proxy_ready(self, timeout_seconds: int = 25) -> bool:
        deadline = time.time() + timeout_seconds

        while time.time() < deadline:
            QApplication.processEvents()

            if self.client_process is None:
                return False

            if self.client_process.poll() is not None:
                return False

            code, output = run_command(
                [
                    "curl",
                    "--max-time",
                    "5",
                    "--silent",
                    "--show-error",
                    "--socks5-hostname",
                    f"{self.socks_host()}:{self.socks_port()}",
                    "https://ifconfig.me",
                ],
                timeout=8,
                windows_no_window=True,
            )

            if code == 0 and output.strip():
                self.append_log(f"Проверка туннеля успешна. IP: {output.strip()}")
                return True

            self.append_log("Ожидание готовности туннеля...")
            time.sleep(2)

        return False

    def connect_client(self):
        try:
            self.set_status("Подключение...")
            self.update_state()
            QApplication.processEvents()

            self.append_log("=== Включение ===")

            self.cleanup_old_client()

            cfg = self.fetch_config()
            self.current_config = cfg

            self.append_log(
                "Конфиг получен:\n"
                f"Provider: {cfg['provider']}\n"
                f"Room ID: {cfg['room_id']}\n"
                f"DNS: {cfg.get('dns_server', DEFAULT_DNS_SERVER)}"
            )

            args = self.build_client_args(cfg)

            self.client_log_path.parent.mkdir(parents=True, exist_ok=True)
            self.client_log_file = open(self.client_log_path, "a", encoding="utf-8", buffering=1)
            self.client_log_position = self.client_log_path.stat().st_size if self.client_log_path.exists() else 0

            self.client_process = self.platform.start_process(args, self.client_log_file)

            self.log_timer.start()
            time.sleep(1)

            if self.client_process.poll() is not None:
                raise RuntimeError("olcRTC client exited immediately. Open logs for details.")

            self.append_log("Проверяю готовность туннеля...")

            if not self.wait_proxy_ready(timeout_seconds=25):
                raise RuntimeError(
                    "Туннель не стал готовым за 25 секунд. "
                    "Системный proxy не включён. Проверь логи сервера."
                )

            self.platform.enable_system_proxy(
                self.socks_host(),
                self.socks_port(),
                self.network_service(),
            )

            if self.settings.get("auto_refresh", True):
                self.config_timer.start()

            self.append_log("Подключено.")
            self.set_status("Включено")
            self.update_state()

        except Exception as exc:
            self.set_status("Ошибка")
            self.append_log(f"Ошибка включения:\n{type(exc).__name__}: {exc}")

            try:
                self.platform.disable_system_proxy(self.network_service())
            except Exception:
                pass

            try:
                self.platform.kill_existing_client()
            except Exception:
                pass

            self.client_process = None
            self.update_state()

    def disconnect_client(self):
        try:
            self.append_log("=== Выключение ===")

            self.config_timer.stop()
            self.log_timer.stop()

            if self.is_running():
                try:
                    self.client_process.terminate()
                    self.client_process.wait(timeout=5)
                except Exception:
                    try:
                        self.client_process.kill()
                        self.client_process.wait(timeout=5)
                    except Exception:
                        pass

            self.client_process = None

            try:
                self.platform.kill_existing_client()
            except Exception:
                pass

            if self.client_log_file is not None:
                try:
                    self.client_log_file.close()
                except Exception:
                    pass

            self.client_log_file = None

            self.platform.disable_system_proxy(self.network_service())
            self.wait_port_free()

            self.append_log("Отключено.")
            self.set_status("Выключено")
            self.update_state()

        except Exception as exc:
            self.set_status("Ошибка")
            self.append_log(f"Ошибка выключения:\n{type(exc).__name__}: {exc}")
            self.update_state()

    def read_client_logs(self):
        try:
            if self.client_log_path.exists():
                with open(self.client_log_path, "r", encoding="utf-8", errors="replace") as f:
                    f.seek(self.client_log_position)
                    new_data = f.read()
                    self.client_log_position = f.tell()

                if new_data:
                    self.append_log(new_data)

        except Exception as exc:
            self.append_log(f"Ошибка чтения логов: {type(exc).__name__}: {exc}")

        if self.client_process is None:
            self.log_timer.stop()
            self.update_state()
            return

        if self.client_process.poll() is not None:
            code = self.client_process.returncode
            self.log_timer.stop()
            self.config_timer.stop()
            self.client_process = None

            try:
                self.platform.disable_system_proxy(self.network_service())
            except Exception:
                pass

            self.set_status("Ошибка")
            self.append_log(f"Клиент завершился с кодом {code}.")
            self.update_state()

    def check_config_update(self):
        if self.is_reconnecting:
            return

        try:
            if not self.is_running():
                return

            new_cfg = self.fetch_config()

            if self.current_config == new_cfg:
                self.append_log("Автопроверка: комната не изменилась.")
                return

            self.append_log("Автопроверка: комната изменилась, переподключаюсь.")

            self.is_reconnecting = True
            self.update_state()

            self.disconnect_client()
            self.current_config = new_cfg
            self.connect_client()

        except Exception as exc:
            self.append_log(f"Ошибка автообновления:\n{type(exc).__name__}: {exc}")

        finally:
            self.is_reconnecting = False
            self.update_state()

    def test_ip(self):
        try:
            self.append_log("=== Проверка IP ===")

            code, output = run_command(
                [
                    "curl",
                    "--max-time",
                    "30",
                    "-v",
                    "--socks5-hostname",
                    f"{self.socks_host()}:{self.socks_port()}",
                    "https://ifconfig.me",
                ],
                timeout=40,
                windows_no_window=True,
            )

            self.append_log(output)

            if code != 0:
                raise RuntimeError(f"curl failed with code {code}")

        except Exception as exc:
            self.append_log(f"Ошибка проверки IP:\n{type(exc).__name__}: {exc}")

    def closeEvent(self, event):
        if self.is_running():
            reply = QMessageBox.question(
                self,
                APP_NAME,
                "Клиент всё ещё включён. Выключить и закрыть приложение?",
                QMessageBox.Yes | QMessageBox.No,
            )

            if reply == QMessageBox.Yes:
                self.disconnect_client()
                event.accept()
            else:
                event.ignore()
        else:
            event.accept()


def run_app(platform: PlatformAdapter, platform_name: str):
    app = QApplication(sys.argv)

    window = MainWindow(platform, platform_name)
    window.show()

    sys.exit(app.exec())