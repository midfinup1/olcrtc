import json
import secrets
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QColor, QPainter, QPalette, QIcon
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QDialog,
    QFrame,
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

# ============================================================
# Константы
# ============================================================

APP_NAME = "BareBone VPN"

CONFIG_REFRESH_INTERVAL_MS = 5 * 60 * 1000
LOG_READ_INTERVAL_MS = 500

DEFAULT_CONFIG_URL = "http://194.58.58.92:8090/connection.json"
DEFAULT_CONFIG_TOKEN = "3311fe77453c1f36d1ad8535470681595c7bf019cf7831a1797e9ce863932973"
DEFAULT_AUTO_FETCH_CONFIG = False

DEFAULT_PROVIDER = "wbstream"
DEFAULT_ROOM_ID = ""
DEFAULT_ENCRYPTION_KEY = ""
DEFAULT_SOCKS_HOST = "127.0.0.1"
DEFAULT_SOCKS_PORT = 8808
DEFAULT_DNS_SERVER = "1.1.1.1:53"
DEFAULT_LINK_TYPE = "direct"
DEFAULT_TRANSPORT = "datachannel"
DEFAULT_NETWORK_SERVICE = "Wi-Fi"

DEFAULT_BOOTSTRAP_ENABLED = True
DEFAULT_BOOTSTRAP_PROVIDER = "wbstream"
DEFAULT_BOOTSTRAP_ROOM_ID = "019dfa7c-5941-74f1-b6d6-ba76c302538d"
DEFAULT_BOOTSTRAP_KEY = "276b40f502d113889da50ed0c0810f959f1090bf56823b931b85a9f5e738b4f6"
DEFAULT_BOOTSTRAP_TOKEN = "87e0229fc6e7f65e65b7582a2b29e32906ad5adb45eed9000f539b9f6ad3c176"
DEFAULT_BOOTSTRAP_DNS_SERVER = "1.1.1.1:53"
DEFAULT_BOOTSTRAP_TIMEOUT_SECONDS = 45

DEFAULT_BOOTSTRAP_ACTION_REGISTER = "register"
DEFAULT_BOOTSTRAP_ACTION_ROTATE = "rotate"
BOOTSTRAP_MODE_NAME = "bootstrap-cnc"

# ============================================================
# Палитра
# ============================================================

C_BG = "#0d0f12"
C_SURFACE = "#14181f"
C_CARD = "#1a1f28"
C_BORDER = "#252b36"
C_ACCENT = "#00e5a0"
C_ACCENT2 = "#0099ff"
C_RED = "#ff4d6a"
C_TEXT = "#e8edf5"
C_MUTED = "#5a6478"
C_LABEL = "#8a95a8"

STYLESHEET = f"""
QWidget {{
    background: {C_BG};
    color: {C_TEXT};
    font-family: 'JetBrains Mono', 'Cascadia Code', 'Fira Code', 'Consolas', monospace;
    font-size: 12px;
}}

QMainWindow, QDialog {{
    background: {C_BG};
}}

QPushButton {{
    background: {C_CARD};
    color: {C_TEXT};
    border: 1px solid {C_BORDER};
    border-radius: 6px;
    padding: 8px 18px;
    font-size: 12px;
    letter-spacing: 0.5px;
}}

QPushButton:hover {{
    background: {C_SURFACE};
    border-color: {C_ACCENT2};
    color: {C_ACCENT2};
}}

QPushButton:pressed {{
    background: {C_BG};
}}

QPushButton:disabled {{
    color: {C_MUTED};
    border-color: {C_BORDER};
    background: {C_BG};
}}

QPushButton#btn_connect {{
    background: qlineargradient(x1:0,y1:0,x2:1,y2:0,
        stop:0 #00b87a, stop:1 #00e5a0);
    color: #001a0f;
    border: none;
    font-weight: 700;
    font-size: 13px;
    border-radius: 8px;
    letter-spacing: 1px;
}}

QPushButton#btn_connect:hover {{
    background: qlineargradient(x1:0,y1:0,x2:1,y2:0,
        stop:0 #00cc88, stop:1 #33ffb8);
}}

QPushButton#btn_connect:disabled {{
    background: {C_CARD};
    color: {C_MUTED};
    border: 1px solid {C_BORDER};
}}

QPushButton#btn_disconnect {{
    background: transparent;
    color: {C_RED};
    border: 1px solid {C_RED};
    font-weight: 600;
    border-radius: 8px;
}}

QPushButton#btn_disconnect:hover {{
    background: rgba(255,77,106,0.12);
}}

QPushButton#btn_disconnect:disabled {{
    color: {C_MUTED};
    border-color: {C_BORDER};
}}

QPushButton#btn_logs {{
    background: {C_SURFACE};
    color: {C_LABEL};
    border: 1px solid {C_BORDER};
    border-radius: 6px;
    padding: 8px 14px;
    font-size: 11px;
}}

QPushButton#btn_logs:hover {{
    border-color: {C_ACCENT2};
    color: {C_ACCENT2};
}}

QPushButton#btn_icon {{
    background: {C_CARD};
    color: {C_LABEL};
    border: 1px solid {C_BORDER};
    border-radius: 6px;
    padding: 0;
    font-size: 16px;
    font-weight: 700;
}}

QPushButton#btn_icon:hover {{
    background: {C_SURFACE};
    border-color: {C_ACCENT2};
    color: {C_ACCENT2};
}}

QPushButton#btn_icon:disabled {{
    background: {C_BG};
    color: {C_MUTED};
    border-color: {C_BORDER};
}}

QLineEdit, QSpinBox {{
    background: {C_SURFACE};
    border: 1px solid {C_BORDER};
    border-radius: 5px;
    padding: 6px 10px;
    color: {C_TEXT};
    selection-background-color: {C_ACCENT2};
}}

QLineEdit:focus, QSpinBox:focus {{
    border-color: {C_ACCENT2};
}}

QSpinBox::up-button, QSpinBox::down-button {{
    background: {C_CARD};
    border: none;
    width: 16px;
}}

QCheckBox {{
    color: {C_LABEL};
    spacing: 8px;
}}

QCheckBox::indicator {{
    width: 16px;
    height: 16px;
    border: 1px solid {C_BORDER};
    border-radius: 3px;
    background: {C_SURFACE};
}}

QCheckBox::indicator:checked {{
    background: {C_ACCENT};
    border-color: {C_ACCENT};
}}

QCheckBox:hover {{
    color: {C_TEXT};
}}

QPlainTextEdit {{
    background: {C_SURFACE};
    border: 1px solid {C_BORDER};
    border-radius: 6px;
    color: #7dffbe;
    font-size: 11px;
    padding: 8px;
    selection-background-color: {C_ACCENT2};
}}

QScrollBar:vertical {{
    background: {C_BG};
    width: 6px;
    border-radius: 3px;
}}

QScrollBar::handle:vertical {{
    background: {C_BORDER};
    border-radius: 3px;
    min-height: 20px;
}}

QScrollBar::handle:vertical:hover {{
    background: {C_MUTED};
}}

QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
    height: 0;
}}
"""

# ============================================================
# Утилиты
# ============================================================

def to_text(value) -> str:
    if value is None:
        return ""

    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")

    return str(value)


def generate_client_id() -> str:
    return "c-" + secrets.token_hex(8)


def get_user_dir() -> Path:
    path = Path.home() / ".BareBoneVPN-manager"
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
        raise RuntimeError("Config URL is empty.")

    if not token:
        raise RuntimeError("Config token is empty.")

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
        raise RuntimeError(
            f"HTTP {exc.code}: {exc.read().decode('utf-8', errors='replace')}"
        ) from exc

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
        raise RuntimeError("connection.json incomplete: need provider, room_id, encryption_key")

    return {
        "provider": provider,
        "room_id": room_id,
        "encryption_key": encryption_key,
        "dns_server": dns_server,
        "transport": data.get("transport", DEFAULT_TRANSPORT),
    }


def validate_manual_config(
    provider: str,
    room_id: str,
    encryption_key: str,
    dns_server: str,
) -> dict:
    provider = provider.strip()
    room_id = room_id.strip()
    encryption_key = encryption_key.strip()
    dns_server = dns_server.strip() or DEFAULT_DNS_SERVER

    if not provider:
        raise RuntimeError("Provider is empty. Open Settings.")

    if provider not in ["wbstream", "jazz", "telemost"]:
        raise RuntimeError("Provider must be wbstream, jazz, or telemost.")

    if not room_id:
        raise RuntimeError("Room ID is empty. Open Settings.")

    if not encryption_key:
        raise RuntimeError("Encryption key is empty. Open Settings.")

    return {
        "provider": provider,
        "room_id": room_id,
        "encryption_key": encryption_key,
        "dns_server": dns_server,
        "transport": DEFAULT_TRANSPORT,
    }


def extract_bootstrap_config(output: str) -> dict:
    marker = "BB_CONFIG_JSON="

    for line in output.splitlines():
        line = line.strip()

        if not line.startswith(marker):
            continue

        raw_json = line[len(marker):].strip()

        try:
            data = json.loads(raw_json)

        except json.JSONDecodeError as exc:
            raise RuntimeError(f"Invalid BB_CONFIG_JSON:\n{raw_json}") from exc

        if data.get("type") != "CONFIG":
            raise RuntimeError(f"Unexpected bootstrap response type: {data.get('type')}")

        required = ["client_id", "provider", "room_id", "encryption_key"]
        missing = [key for key in required if not str(data.get(key, "")).strip()]

        if missing:
            raise RuntimeError(f"Bootstrap config is incomplete. Missing: {', '.join(missing)}")

        return {
            "client_id": str(data.get("client_id", "")).strip(),
            "provider": str(data.get("provider", DEFAULT_PROVIDER)).strip() or DEFAULT_PROVIDER,
            "room_id": str(data.get("room_id", "")).strip(),
            "encryption_key": str(data.get("encryption_key", "")).strip(),
            "transport": str(data.get("transport", DEFAULT_TRANSPORT)).strip() or DEFAULT_TRANSPORT,
            "dns_server": str(data.get("dns_server", DEFAULT_DNS_SERVER)).strip() or DEFAULT_DNS_SERVER,
        }

    raise RuntimeError(f"BB_CONFIG_JSON not found in bootstrap output:\n{output}")


# ============================================================
# UI-компоненты
# ============================================================

class StatusOrb(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)

        self.setFixedSize(14, 14)

        self._state = "off"
        self._pulse = 0.0
        self._direction = 1

        self._timer = QTimer(self)
        self._timer.setInterval(30)
        self._timer.timeout.connect(self._tick)
        self._timer.start()

    def set_state(self, state: str):
        self._state = state
        self.update()

    def _tick(self):
        if self._state in ("connecting", "on"):
            self._pulse += 0.05 * self._direction

            if self._pulse >= 1.0:
                self._pulse = 1.0
                self._direction = -1

            elif self._pulse <= 0.0:
                self._pulse = 0.0
                self._direction = 1

        else:
            self._pulse = 0.0

        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        colors = {
            "off": QColor(C_MUTED),
            "connecting": QColor(C_ACCENT2),
            "on": QColor(C_ACCENT),
            "error": QColor(C_RED),
        }

        color = colors.get(self._state, QColor(C_MUTED))

        if self._state in ("on", "connecting") and self._pulse > 0:
            glow = QColor(color)
            glow.setAlphaF(0.25 * self._pulse)
            painter.setBrush(glow)
            painter.setPen(Qt.NoPen)
            painter.drawEllipse(0, 0, 14, 14)

        painter.setBrush(color)
        painter.setPen(Qt.NoPen)
        painter.drawEllipse(3, 3, 8, 8)


class Card(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)

        self.setFrameShape(QFrame.NoFrame)
        self.setStyleSheet(
            f"background: {C_CARD}; border: 1px solid {C_BORDER}; border-radius: 10px;"
        )


class Divider(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)

        self.setFrameShape(QFrame.HLine)
        self.setFrameShadow(QFrame.Plain)
        self.setStyleSheet(
            f"color: {C_BORDER}; background: {C_BORDER}; max-height: 1px;"
        )


class TagLabel(QLabel):
    def __init__(self, text: str, color: str = C_ACCENT2, parent=None):
        super().__init__(text, parent)

        self.setStyleSheet(
            f"color: {color}; background: rgba(0,153,255,0.10); "
            f"border: 1px solid rgba(0,153,255,0.25); border-radius: 4px; "
            f"padding: 1px 7px; font-size: 10px; letter-spacing: 0.5px;"
        )


# ============================================================
# Диалог настроек
# ============================================================

class SettingsDialog(QDialog):
    def __init__(self, parent, settings: dict, platform_name: str):
        super().__init__(parent)

        self.setWindowTitle("Настройки — BareBone VPN")
        self.setFixedWidth(560)
        self.setStyleSheet(
            STYLESHEET
            + f"""
            QDialog {{
                background: {C_BG};
                border: 1px solid {C_BORDER};
                border-radius: 12px;
            }}
        """
        )

        s = settings

        self.bootstrap_enabled_checkbox = QCheckBox(
            "Использовать начальную комнату для получения личной комнаты"
        )
        self.bootstrap_enabled_checkbox.setChecked(
            bool(s.get("bootstrap_enabled", DEFAULT_BOOTSTRAP_ENABLED))
        )

        self.client_id_input = QLineEdit(s.get("client_id", ""))
        self.client_id_input.setReadOnly(True)

        self.bootstrap_room_input = QLineEdit(
            s.get("bootstrap_room_id", DEFAULT_BOOTSTRAP_ROOM_ID)
        )

        self.bootstrap_key_input = QLineEdit(
            s.get("bootstrap_key", DEFAULT_BOOTSTRAP_KEY)
        )
        self.bootstrap_key_input.setEchoMode(QLineEdit.Password)

        self.bootstrap_token_input = QLineEdit(
            s.get("bootstrap_token", DEFAULT_BOOTSTRAP_TOKEN)
        )
        self.bootstrap_token_input.setEchoMode(QLineEdit.Password)

        self.auto_fetch_config_checkbox = QCheckBox("")
        self.auto_fetch_config_checkbox.setChecked(False)
        self.auto_fetch_config_checkbox.hide()

        self.config_url_input = QLineEdit(s.get("config_url", DEFAULT_CONFIG_URL))
        self.config_url_input.hide()

        self.config_token_input = QLineEdit(s.get("config_token", DEFAULT_CONFIG_TOKEN))
        self.config_token_input.setEchoMode(QLineEdit.Password)
        self.config_token_input.hide()

        self.provider_input = QLineEdit(s.get("provider", DEFAULT_PROVIDER))
        self.room_id_input = QLineEdit(s.get("room_id", DEFAULT_ROOM_ID))

        self.encryption_key_input = QLineEdit(
            s.get("encryption_key", DEFAULT_ENCRYPTION_KEY)
        )
        self.encryption_key_input.setEchoMode(QLineEdit.Password)

        self.dns_input = QLineEdit(s.get("dns_server", DEFAULT_DNS_SERVER))
        self.socks_host_input = QLineEdit(s.get("socks_host", DEFAULT_SOCKS_HOST))

        self.socks_port_input = QSpinBox()
        self.socks_port_input.setRange(1, 65535)
        self.socks_port_input.setValue(int(s.get("socks_port", DEFAULT_SOCKS_PORT)))

        self.network_service_input = QLineEdit(
            s.get("network_service", DEFAULT_NETWORK_SERVICE)
        )

        self.auto_connect_checkbox = QCheckBox("Подключаться автоматически при запуске")
        self.auto_connect_checkbox.setChecked(bool(s.get("auto_connect", False)))

        self.auto_refresh_checkbox = QCheckBox("")
        self.auto_refresh_checkbox.setChecked(False)
        self.auto_refresh_checkbox.hide()

        layout = QVBoxLayout(self)
        layout.setSpacing(16)
        layout.setContentsMargins(24, 24, 24, 24)

        title = QLabel("НАСТРОЙКИ")
        title.setStyleSheet(
            f"color: {C_MUTED}; font-size: 10px; letter-spacing: 2px;"
        )
        layout.addWidget(title)

        layout.addWidget(self._section("НАЧАЛЬНАЯ КОМНАТА"))
        layout.addWidget(self.bootstrap_enabled_checkbox)
        layout.addLayout(self._row("Client ID", self.client_id_input))
        layout.addLayout(self._row("Bootstrap Room", self.bootstrap_room_input))
        layout.addLayout(self._row("Bootstrap Key", self.bootstrap_key_input))
        layout.addLayout(self._row("Bootstrap Token", self.bootstrap_token_input))
        layout.addWidget(Divider())

        layout.addWidget(self._section("РУЧНОЕ ПОДКЛЮЧЕНИЕ"))
        layout.addLayout(self._row("Провайдер", self.provider_input))
        layout.addLayout(self._row("Room ID", self.room_id_input))
        layout.addLayout(self._row("Ключ шифрования", self.encryption_key_input))
        layout.addLayout(self._row("DNS", self.dns_input))
        layout.addWidget(Divider())

        layout.addWidget(self._section("ПРОКСИ"))
        layout.addLayout(self._row("SOCKS5 хост", self.socks_host_input))
        layout.addLayout(self._row("SOCKS5 порт", self.socks_port_input))

        if platform_name == "macos":
            layout.addLayout(self._row("Network Service", self.network_service_input))

        layout.addWidget(Divider())

        layout.addWidget(self._section("ДОПОЛНИТЕЛЬНО"))
        layout.addWidget(self.auto_connect_checkbox)

        close_btn = QPushButton("Сохранить и закрыть")
        close_btn.setMinimumHeight(38)
        close_btn.clicked.connect(self.accept)

        layout.addSpacing(4)
        layout.addWidget(close_btn)

        for widget in [
            self.bootstrap_room_input,
            self.bootstrap_key_input,
            self.bootstrap_token_input,
            self.config_url_input,
            self.config_token_input,
            self.provider_input,
            self.room_id_input,
            self.encryption_key_input,
            self.dns_input,
            self.socks_host_input,
            self.network_service_input,
        ]:
            widget.textChanged.connect(self.auto_save_to_parent)

        self.socks_port_input.valueChanged.connect(self.auto_save_to_parent)

        for checkbox in [
            self.bootstrap_enabled_checkbox,
            self.auto_connect_checkbox,
            self.auto_refresh_checkbox,
            self.auto_fetch_config_checkbox,
        ]:
            checkbox.stateChanged.connect(self.auto_save_to_parent)

        self.bootstrap_enabled_checkbox.stateChanged.connect(self.update_fields_state)

        self.update_fields_state()

    def _section(self, text: str) -> QLabel:
        label = QLabel(text)
        label.setStyleSheet(
            f"color: {C_MUTED}; font-size: 10px; letter-spacing: 1.5px; margin-top: 4px;"
        )
        return label

    def _row(self, label: str, widget: QWidget) -> QHBoxLayout:
        label_widget = QLabel(label)
        label_widget.setFixedWidth(150)
        label_widget.setStyleSheet(f"color: {C_LABEL}; font-size: 11px;")

        row = QHBoxLayout()
        row.setSpacing(12)
        row.addWidget(label_widget)
        row.addWidget(widget)

        return row

    def auto_save_to_parent(self):
        parent = self.parent()

        if parent is None:
            return

        if not hasattr(parent, "settings") or not hasattr(parent, "save_settings"):
            return

        parent.settings = self.values()
        parent.save_settings()

        if hasattr(parent, "update_state"):
            parent.update_state()

    def update_fields_state(self):
        bootstrap_enabled = self.bootstrap_enabled_checkbox.isChecked()

        self.bootstrap_room_input.setEnabled(bootstrap_enabled)
        self.bootstrap_key_input.setEnabled(bootstrap_enabled)
        self.bootstrap_token_input.setEnabled(bootstrap_enabled)

        manual_enabled = not bootstrap_enabled

        self.provider_input.setEnabled(manual_enabled)
        self.room_id_input.setEnabled(manual_enabled)
        self.encryption_key_input.setEnabled(manual_enabled)

    def values(self) -> dict:
        old = {}

        parent = self.parent()
        if parent is not None and hasattr(parent, "settings"):
            old = dict(parent.settings)

        return {
            "bootstrap_enabled": self.bootstrap_enabled_checkbox.isChecked(),
            "bootstrap_provider": DEFAULT_BOOTSTRAP_PROVIDER,
            "bootstrap_room_id": self.bootstrap_room_input.text().strip() or DEFAULT_BOOTSTRAP_ROOM_ID,
            "bootstrap_key": self.bootstrap_key_input.text().strip() or DEFAULT_BOOTSTRAP_KEY,
            "bootstrap_token": self.bootstrap_token_input.text().strip() or DEFAULT_BOOTSTRAP_TOKEN,
            "bootstrap_dns_server": DEFAULT_BOOTSTRAP_DNS_SERVER,

            "client_id": old.get("client_id")
            or self.client_id_input.text().strip()
            or generate_client_id(),

            "personal_provider": old.get("personal_provider", ""),
            "personal_room_id": old.get("personal_room_id", ""),
            "personal_encryption_key": old.get("personal_encryption_key", ""),
            "personal_transport": old.get("personal_transport", ""),
            "personal_dns_server": old.get("personal_dns_server", ""),

            "auto_fetch_config": False,
            "config_url": self.config_url_input.text().strip() or DEFAULT_CONFIG_URL,
            "config_token": self.config_token_input.text().strip() or DEFAULT_CONFIG_TOKEN,

            "provider": self.provider_input.text().strip() or DEFAULT_PROVIDER,
            "room_id": self.room_id_input.text().strip(),
            "encryption_key": self.encryption_key_input.text().strip(),
            "dns_server": self.dns_input.text().strip() or DEFAULT_DNS_SERVER,

            "socks_host": self.socks_host_input.text().strip() or DEFAULT_SOCKS_HOST,
            "socks_port": int(self.socks_port_input.value()),
            "network_service": self.network_service_input.text().strip() or DEFAULT_NETWORK_SERVICE,

            "auto_connect": self.auto_connect_checkbox.isChecked(),
            "auto_refresh": False,
        }

    def accept(self):
        self.auto_save_to_parent()
        super().accept()

    def closeEvent(self, event):
        self.auto_save_to_parent()
        event.accept()


# ============================================================
# Платформенный адаптер
# ============================================================

class PlatformAdapter:
    binary_name = "BareBoneVPN"

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


# ============================================================
# Главное окно
# ============================================================

class MainWindow(QMainWindow):
    def __init__(self, platform: PlatformAdapter, platform_name: str):
        super().__init__()

        self.platform = platform
        self.platform_name = platform_name

        self.setWindowTitle(APP_NAME)
        self.setMinimumWidth(480)
        self.setStyleSheet(STYLESHEET)

        self.client_process = None
        self.client_log_file = None
        self.client_log_path = get_log_path()
        self.client_log_position = 0
        self.current_config = None
        self.is_reconnecting = False

        self.settings = self.load_settings()
        self.save_settings()

        self.log_timer = QTimer(self)
        self.log_timer.setInterval(LOG_READ_INTERVAL_MS)
        self.log_timer.timeout.connect(self.read_client_logs)

        self.config_timer = QTimer(self)
        self.config_timer.setInterval(CONFIG_REFRESH_INTERVAL_MS)
        self.config_timer.timeout.connect(self.check_config_update)

        self._build_ui()

        if self.settings.get("auto_connect", False):
            QTimer.singleShot(500, self.connect_client)

    # ----------------------------------------------------------
    # UI
    # ----------------------------------------------------------

    def _build_ui(self):
        root = QWidget()

        root_layout = QVBoxLayout(root)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        top_widget = QWidget()

        top_layout = QVBoxLayout(top_widget)
        top_layout.setContentsMargins(20, 20, 20, 14)
        top_layout.setSpacing(14)

        header = QHBoxLayout()

        logo_label = QLabel("●  BareBone")
        logo_label.setStyleSheet(
            f"color: {C_ACCENT}; font-size: 18px; font-weight: 700; letter-spacing: 2px;"
        )

        self._provider_tag = TagLabel("wbstream")
        self._mode_tag = TagLabel("bootstrap", C_MUTED)

        header.addWidget(logo_label)
        header.addSpacing(10)
        header.addWidget(self._provider_tag)
        header.addWidget(self._mode_tag)
        header.addStretch()

        self.rotate_button = QPushButton("↻")
        self.rotate_button.setObjectName("btn_icon")
        self.rotate_button.setFixedSize(32, 32)
        self.rotate_button.setToolTip("Обновить личную комнату")
        self.rotate_button.clicked.connect(self.rotate_personal_room)

        settings_button = QPushButton("⚙")
        settings_button.setObjectName("btn_icon")
        settings_button.setFixedSize(32, 32)
        settings_button.setToolTip("Настройки")
        settings_button.clicked.connect(self.open_settings)

        header.addWidget(self.rotate_button)
        header.addWidget(settings_button)

        top_layout.addLayout(header)

        status_card = Card()
        status_card.setFixedHeight(95)

        status_layout = QVBoxLayout(status_card)
        status_layout.setContentsMargins(20, 16, 20, 16)
        status_layout.setSpacing(6)

        status_row = QHBoxLayout()

        self._orb = StatusOrb()

        self._status_label = QLabel("ВЫКЛЮЧЕНО")
        self._status_label.setStyleSheet(
            f"color: {C_TEXT}; font-size: 20px; font-weight: 700; letter-spacing: 2px;"
        )

        status_row.addWidget(self._orb, alignment=Qt.AlignVCenter)
        status_row.addSpacing(8)
        status_row.addWidget(self._status_label, alignment=Qt.AlignVCenter)
        status_row.addStretch()

        status_layout.addLayout(status_row)

        self._addr_label = QLabel("SOCKS5  127.0.0.1:8808")
        self._addr_label.setStyleSheet(
            f"color: {C_MUTED}; font-size: 11px; letter-spacing: 0.5px;"
        )
        status_layout.addWidget(self._addr_label)

        self._client_label = QLabel("")
        self._client_label.hide()

        self._room_label = QLabel("")
        self._room_label.hide()

        top_layout.addWidget(status_card)

        button_row = QHBoxLayout()
        button_row.setSpacing(10)

        self.connect_button = QPushButton("ВКЛЮЧИТЬ")
        self.connect_button.setObjectName("btn_connect")
        self.connect_button.setMinimumHeight(46)

        self.disconnect_button = QPushButton("ВЫКЛЮЧИТЬ")
        self.disconnect_button.setObjectName("btn_disconnect")
        self.disconnect_button.setMinimumHeight(46)

        self.logs_button = QPushButton("Логи ▼")
        self.logs_button.setObjectName("btn_logs")
        self.logs_button.setFixedWidth(90)
        self.logs_button.setMinimumHeight(46)

        button_row.addWidget(self.connect_button, 3)
        button_row.addWidget(self.disconnect_button, 2)
        button_row.addWidget(self.logs_button)

        top_layout.addLayout(button_row)

        root_layout.addWidget(top_widget)

        log_widget = QWidget()

        log_layout = QVBoxLayout(log_widget)
        log_layout.setContentsMargins(20, 0, 20, 14)
        log_layout.setSpacing(6)

        self.output = QPlainTextEdit()
        self.output.setReadOnly(True)
        self.output.setLineWrapMode(QPlainTextEdit.NoWrap)
        self.output.setMinimumHeight(180)

        log_layout.addWidget(self.output)

        footer = QLabel("BareBone VPN Manager  •  WebRTC tunnel")
        footer.setStyleSheet(
            f"color: {C_MUTED}; font-size: 10px; letter-spacing: 0.5px;"
        )
        footer.setAlignment(Qt.AlignCenter)

        log_layout.addWidget(footer)

        self._log_widget = log_widget
        self._log_widget.hide()

        root_layout.addWidget(self._log_widget, 1)

        self.setCentralWidget(root)

        self.connect_button.clicked.connect(self.connect_client)
        self.disconnect_button.clicked.connect(self.disconnect_client)
        self.logs_button.clicked.connect(self.toggle_logs)

        self.update_state()
        self.adjustSize()

    # ----------------------------------------------------------
    # Состояние UI
    # ----------------------------------------------------------

    def update_state(self):
        running = self.is_running()

        if running:
            self._set_status("ВКЛЮЧЕНО", "on")

        elif self.is_reconnecting:
            self._set_status("ПЕРЕПОДКЛЮЧЕНИЕ...", "connecting")

        else:
            self._set_status("ВЫКЛЮЧЕНО", "off")

        mode = self.connection_mode_label()
        provider = self.active_provider_label()

        self._provider_tag.setText(provider)
        self._mode_tag.setText(mode)

        self._addr_label.setText(
            f"SOCKS5  {self.socks_host()}:{self.socks_port()}  "
            f"•  HTTP  {self.socks_host()}:{self.socks_port() + 1}"
        )

        self._client_label.setText("")
        self._room_label.setText("")

        self.connect_button.setEnabled(not running and not self.is_reconnecting)
        self.disconnect_button.setEnabled(running or self.is_reconnecting)

        self.rotate_button.setEnabled(
            not self.is_reconnecting
            and bool(self.settings.get("bootstrap_enabled", True))
        )

    def connection_mode_label(self) -> str:
        if self.settings.get("bootstrap_enabled", DEFAULT_BOOTSTRAP_ENABLED):
            return "bootstrap"

        return "manual"

    def active_provider_label(self) -> str:
        if self.settings.get("bootstrap_enabled", DEFAULT_BOOTSTRAP_ENABLED):
            return (
                self.settings.get("personal_provider")
                or self.settings.get("bootstrap_provider", DEFAULT_BOOTSTRAP_PROVIDER)
            )

        return self.settings.get("provider", DEFAULT_PROVIDER)

    def _set_status(self, text: str, state: str):
        colors = {
            "off": C_MUTED,
            "connecting": C_ACCENT2,
            "on": C_ACCENT,
            "error": C_RED,
        }

        color = colors.get(state, C_MUTED)

        self._status_label.setText(text)
        self._status_label.setStyleSheet(
            f"color: {color}; font-size: 20px; font-weight: 700; letter-spacing: 2px;"
        )
        self._orb.set_state(state)

    def toggle_logs(self):
        visible = self._log_widget.isVisible()

        self._log_widget.setVisible(not visible)
        self.logs_button.setText("Логи ▲" if not visible else "Логи ▼")

        self.adjustSize()

    def append_log(self, text: str):
        if not text:
            return

        self.output.appendPlainText(str(text).rstrip())
        self.output.verticalScrollBar().setValue(
            self.output.verticalScrollBar().maximum()
        )

    def open_settings(self):
        dialog = SettingsDialog(self, self.settings, self.platform_name)
        dialog.exec()

        self.settings = dialog.values()
        self.save_settings()
        self.update_state()
        self.append_log("Настройки сохранены.")

    # ----------------------------------------------------------
    # Настройки
    # ----------------------------------------------------------

    def load_settings(self) -> dict:
        defaults = {
            "bootstrap_enabled": DEFAULT_BOOTSTRAP_ENABLED,
            "bootstrap_provider": DEFAULT_BOOTSTRAP_PROVIDER,
            "bootstrap_room_id": DEFAULT_BOOTSTRAP_ROOM_ID,
            "bootstrap_key": DEFAULT_BOOTSTRAP_KEY,
            "bootstrap_token": DEFAULT_BOOTSTRAP_TOKEN,
            "bootstrap_dns_server": DEFAULT_BOOTSTRAP_DNS_SERVER,

            "client_id": "",

            "personal_provider": "",
            "personal_room_id": "",
            "personal_encryption_key": "",
            "personal_transport": "",
            "personal_dns_server": "",

            "auto_fetch_config": False,
            "config_url": DEFAULT_CONFIG_URL,
            "config_token": DEFAULT_CONFIG_TOKEN,

            "provider": DEFAULT_PROVIDER,
            "room_id": DEFAULT_ROOM_ID,
            "encryption_key": DEFAULT_ENCRYPTION_KEY,
            "dns_server": DEFAULT_DNS_SERVER,

            "socks_host": DEFAULT_SOCKS_HOST,
            "socks_port": DEFAULT_SOCKS_PORT,
            "network_service": DEFAULT_NETWORK_SERVICE,

            "auto_connect": False,
            "auto_refresh": False,
        }

        path = get_settings_path()

        if not path.exists():
            defaults["client_id"] = generate_client_id()
            return defaults

        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            defaults.update(data)

            defaults["auto_fetch_config"] = False
            defaults["auto_refresh"] = False

            if not str(defaults.get("client_id", "")).strip():
                defaults["client_id"] = generate_client_id()

            for key, value in [
                ("bootstrap_provider", DEFAULT_BOOTSTRAP_PROVIDER),
                ("bootstrap_room_id", DEFAULT_BOOTSTRAP_ROOM_ID),
                ("bootstrap_key", DEFAULT_BOOTSTRAP_KEY),
                ("bootstrap_token", DEFAULT_BOOTSTRAP_TOKEN),
                ("bootstrap_dns_server", DEFAULT_BOOTSTRAP_DNS_SERVER),
                ("config_url", DEFAULT_CONFIG_URL),
                ("config_token", DEFAULT_CONFIG_TOKEN),
                ("provider", DEFAULT_PROVIDER),
                ("dns_server", DEFAULT_DNS_SERVER),
            ]:
                if not defaults.get(key):
                    defaults[key] = value

            return defaults

        except Exception:
            defaults["client_id"] = generate_client_id()
            return defaults

    def save_settings(self):
        get_settings_path().write_text(
            json.dumps(self.settings, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def socks_host(self) -> str:
        return self.settings.get("socks_host", DEFAULT_SOCKS_HOST)

    def socks_port(self) -> int:
        return int(self.settings.get("socks_port", DEFAULT_SOCKS_PORT))

    def network_service(self) -> str:
        return self.settings.get("network_service", DEFAULT_NETWORK_SERVICE)

    def is_running(self) -> bool:
        return self.client_process is not None and self.client_process.poll() is None

    # ----------------------------------------------------------
    # Bootstrap
    # ----------------------------------------------------------

    def bootstrap_config_present(self) -> bool:
        return bool(
            str(self.settings.get("personal_room_id", "")).strip()
            and str(self.settings.get("personal_encryption_key", "")).strip()
        )

    def run_bootstrap(self, action: str) -> dict:
        binary = self.platform.binary_path()

        if not binary.exists():
            raise RuntimeError(f"BareBoneVPN binary not found: {binary}")

        if sys.platform != "win32":
            binary.chmod(0o755)

        client_id = str(self.settings.get("client_id", "")).strip()

        if not client_id:
            client_id = generate_client_id()
            self.settings["client_id"] = client_id
            self.save_settings()

        bootstrap_provider = str(
            self.settings.get("bootstrap_provider", DEFAULT_BOOTSTRAP_PROVIDER)
        ).strip()

        bootstrap_room_id = str(
            self.settings.get("bootstrap_room_id", DEFAULT_BOOTSTRAP_ROOM_ID)
        ).strip()

        bootstrap_key = str(
            self.settings.get("bootstrap_key", DEFAULT_BOOTSTRAP_KEY)
        ).strip()

        bootstrap_token = str(
            self.settings.get("bootstrap_token", DEFAULT_BOOTSTRAP_TOKEN)
        ).strip()

        bootstrap_dns = str(
            self.settings.get("bootstrap_dns_server", DEFAULT_BOOTSTRAP_DNS_SERVER)
        ).strip()

        if not bootstrap_provider:
            raise RuntimeError("Bootstrap provider is empty.")

        if not bootstrap_room_id:
            raise RuntimeError("Bootstrap room id is empty.")

        if not bootstrap_key:
            raise RuntimeError("Bootstrap key is empty.")

        if not bootstrap_token:
            raise RuntimeError("Bootstrap token is empty.")

        data_dir = get_data_dir() / "bootstrap"
        data_dir.mkdir(parents=True, exist_ok=True)

        args = [
            str(binary),
            "-mode", BOOTSTRAP_MODE_NAME,
            "-link", DEFAULT_LINK_TYPE,
            "-transport", DEFAULT_TRANSPORT,
            "-provider", bootstrap_provider,
            "-id", bootstrap_room_id,
            "-key", bootstrap_key,
            "-data", str(data_dir),
            "-dns", bootstrap_dns,
            "-bootstrap-action", action,
            "-client-id", client_id,
            "-bootstrap-token", bootstrap_token,
        ]

        self.append_log(f"Bootstrap: action={action}, client_id={client_id}")

        code, output = run_command(
            args,
            timeout=DEFAULT_BOOTSTRAP_TIMEOUT_SECONDS,
            windows_no_window=True,
        )

        self.append_log(output)

        if code != 0:
            raise RuntimeError(f"Bootstrap failed with code {code}")

        cfg = extract_bootstrap_config(output)

        self.settings.update(
            {
                "client_id": cfg["client_id"],
                "personal_provider": cfg["provider"],
                "personal_room_id": cfg["room_id"],
                "personal_encryption_key": cfg["encryption_key"],
                "personal_transport": cfg["transport"],
                "personal_dns_server": cfg["dns_server"],

                "provider": cfg["provider"],
                "room_id": cfg["room_id"],
                "encryption_key": cfg["encryption_key"],
                "dns_server": cfg["dns_server"],
            }
        )

        self.save_settings()

        self.append_log(f"Получена личная комната: {cfg['room_id']}")

        return cfg

    def rotate_personal_room(self):
        was_running = self.is_running()

        try:
            self.is_reconnecting = True
            self._set_status("ОБНОВЛЕНИЕ...", "connecting")
            self.update_state()
            QApplication.processEvents()

            self.append_log("=== Обновление личной комнаты ===")

            if was_running:
                self.append_log("Текущий туннель включён. Выполняю безопасное переподключение.")
                self.disconnect_client()

            cfg = self.run_bootstrap(DEFAULT_BOOTSTRAP_ACTION_ROTATE)
            self.current_config = cfg

            self.append_log("Личная комната обновлена.")

            if was_running:
                self.append_log("Переподключение к новой личной комнате.")
                self.is_reconnecting = False
                self.connect_client()
            else:
                self.is_reconnecting = False
                self._set_status("ВЫКЛЮЧЕНО", "off")
                self.update_state()

        except Exception as exc:
            self.is_reconnecting = False
            self._set_status("ОШИБКА", "error")
            self.append_log(
                f"Ошибка обновления комнаты: {type(exc).__name__}: {exc}"
            )

            if was_running and not self.is_running():
                self.append_log("Пробую вернуть подключение на текущих сохранённых настройках.")

                try:
                    self.connect_client()
                except Exception as reconnect_exc:
                    self.append_log(
                        f"Не удалось восстановить подключение: {type(reconnect_exc).__name__}: {reconnect_exc}"
                    )

            self.update_state()

    # ----------------------------------------------------------
    # Подключение
    # ----------------------------------------------------------

    def get_connection_config(self) -> dict:
        if self.settings.get("bootstrap_enabled", DEFAULT_BOOTSTRAP_ENABLED):
            if not self.bootstrap_config_present():
                return self.run_bootstrap(DEFAULT_BOOTSTRAP_ACTION_REGISTER)

            return {
                "provider": self.settings.get("personal_provider") or DEFAULT_PROVIDER,
                "room_id": self.settings.get("personal_room_id", ""),
                "encryption_key": self.settings.get("personal_encryption_key", ""),
                "dns_server": self.settings.get("personal_dns_server") or DEFAULT_DNS_SERVER,
                "transport": self.settings.get("personal_transport") or DEFAULT_TRANSPORT,
            }

        return validate_manual_config(
            self.settings.get("provider", DEFAULT_PROVIDER),
            self.settings.get("room_id", ""),
            self.settings.get("encryption_key", ""),
            self.settings.get("dns_server", DEFAULT_DNS_SERVER),
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
            raise RuntimeError(f"BareBoneVPN binary not found: {binary}")

        if sys.platform != "win32":
            binary.chmod(0o755)

        return [
            str(binary),
            "-mode", "cnc",
            "-link", DEFAULT_LINK_TYPE,
            "-transport", cfg.get("transport", DEFAULT_TRANSPORT),
            "-provider", cfg["provider"],
            "-id", cfg["room_id"],
            "-key", cfg["encryption_key"],
            "-data", str(get_data_dir()),
            "-dns", cfg.get("dns_server", DEFAULT_DNS_SERVER),
            "-socks-host", self.socks_host(),
            "-socks-port", str(self.socks_port()),
        ]

    def wait_proxy_ready(self, timeout_seconds: int = 25) -> bool:
        deadline = time.time() + timeout_seconds

        while time.time() < deadline:
            QApplication.processEvents()

            if self.client_process is None or self.client_process.poll() is not None:
                return False

            code, output = run_command(
                [
                    "curl",
                    "--max-time", "5",
                    "--silent",
                    "--show-error",
                    "--socks5-hostname", f"{self.socks_host()}:{self.socks_port()}",
                    "https://ifconfig.me",
                ],
                timeout=8,
                windows_no_window=True,
            )

            if code == 0 and output.strip():
                self.append_log(f"Туннель готов. IP выхода: {output.strip()}")
                return True

            self.append_log("Ожидание туннеля...")
            time.sleep(2)

        return False

    def connect_client(self):
        try:
            self._set_status("ПОДКЛЮЧЕНИЕ...", "connecting")
            QApplication.processEvents()

            self.append_log("=== Включение ===")
            self.save_settings()
            self.cleanup_old_client()

            cfg = self.get_connection_config()
            self.current_config = cfg

            self.append_log(
                f"Provider: {cfg['provider']}  |  Room: {cfg['room_id']}  |  "
                f"DNS: {cfg.get('dns_server', DEFAULT_DNS_SERVER)}"
            )

            args = self.build_client_args(cfg)

            self.client_log_path.parent.mkdir(parents=True, exist_ok=True)

            self.client_log_file = open(
                self.client_log_path,
                "a",
                encoding="utf-8",
                buffering=1,
            )

            self.client_log_position = (
                self.client_log_path.stat().st_size
                if self.client_log_path.exists()
                else 0
            )

            self.client_process = self.platform.start_process(
                args,
                self.client_log_file,
            )

            self.log_timer.start()

            time.sleep(1)

            if self.client_process.poll() is not None:
                raise RuntimeError("BareBoneVPN вышел сразу. Смотри логи.")

            if not self.wait_proxy_ready(timeout_seconds=25):
                raise RuntimeError("Туннель не поднялся за 25 сек. Проверь комнату и ключ.")

            self.platform.enable_system_proxy(
                self.socks_host(),
                self.socks_port(),
                self.network_service(),
            )

            self.config_timer.stop()

            self.append_log("Подключено.")
            self._set_status("ВКЛЮЧЕНО", "on")
            self.update_state()

        except Exception as exc:
            self._set_status("ОШИБКА", "error")
            self.append_log(f"Ошибка: {type(exc).__name__}: {exc}")

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
            self._set_status("ВЫКЛЮЧЕНО", "off")
            self.update_state()

        except Exception as exc:
            self._set_status("ОШИБКА", "error")
            self.append_log(f"Ошибка выключения: {exc}")
            self.update_state()

    def read_client_logs(self):
        try:
            if self.client_log_path.exists():
                with open(
                    self.client_log_path,
                    "r",
                    encoding="utf-8",
                    errors="replace",
                ) as file:
                    file.seek(self.client_log_position)
                    new_data = file.read()
                    self.client_log_position = file.tell()

                if new_data:
                    self.append_log(new_data)

        except Exception as exc:
            self.append_log(f"Ошибка чтения логов: {exc}")

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

            self._set_status("ОШИБКА", "error")
            self.append_log(f"Клиент завершился с кодом {code}.")
            self.update_state()

    def check_config_update(self):
        return

    def closeEvent(self, event):
        if self.is_running():
            reply = QMessageBox.question(
                self,
                APP_NAME,
                "Клиент всё ещё включён. Выключить и закрыть?",
                QMessageBox.Yes | QMessageBox.No,
            )

            if reply == QMessageBox.Yes:
                self.disconnect_client()
                event.accept()

            else:
                event.ignore()

        else:
            event.accept()


# ============================================================
# Точка входа
# ============================================================

def run_app(platform: PlatformAdapter, platform_name: str):
    app = QApplication(sys.argv)
    app.setStyle("Fusion")

    icon_path = Path(__file__).resolve().parent / "assets" / "icon.png"

    if icon_path.exists():
        app.setWindowIcon(QIcon(str(icon_path)))

    palette = QPalette()
    palette.setColor(QPalette.Window, QColor(C_BG))
    palette.setColor(QPalette.WindowText, QColor(C_TEXT))
    palette.setColor(QPalette.Base, QColor(C_SURFACE))
    palette.setColor(QPalette.AlternateBase, QColor(C_CARD))
    palette.setColor(QPalette.Text, QColor(C_TEXT))
    palette.setColor(QPalette.Button, QColor(C_CARD))
    palette.setColor(QPalette.ButtonText, QColor(C_TEXT))
    palette.setColor(QPalette.Highlight, QColor(C_ACCENT2))
    palette.setColor(QPalette.HighlightedText, QColor("#ffffff"))

    app.setPalette(palette)

    window = MainWindow(platform, platform_name)

    if icon_path.exists():
        window.setWindowIcon(QIcon(str(icon_path)))

    window.show()

    sys.exit(app.exec())