import json
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QColor, QPainter, QPalette
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

# ============================================================
# Палитра
# ============================================================

C_BG      = "#0d0f12"
C_SURFACE = "#14181f"
C_CARD    = "#1a1f28"
C_BORDER  = "#252b36"
C_ACCENT  = "#00e5a0"
C_ACCENT2 = "#0099ff"
C_RED     = "#ff4d6a"
C_TEXT    = "#e8edf5"
C_MUTED   = "#5a6478"
C_LABEL   = "#8a95a8"

STYLESHEET = f"""
QWidget {{
    background: {C_BG};
    color: {C_TEXT};
    font-family: 'JetBrains Mono', 'Cascadia Code', 'Fira Code', 'Consolas', monospace;
    font-size: 12px;
}}
QMainWindow, QDialog {{ background: {C_BG}; }}

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
QPushButton:pressed {{ background: {C_BG}; }}
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
QPushButton#btn_disconnect:hover {{ background: rgba(255,77,106,0.12); }}
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

QLineEdit, QSpinBox {{
    background: {C_SURFACE};
    border: 1px solid {C_BORDER};
    border-radius: 5px;
    padding: 6px 10px;
    color: {C_TEXT};
    selection-background-color: {C_ACCENT2};
}}
QLineEdit:focus, QSpinBox:focus {{ border-color: {C_ACCENT2}; }}
QSpinBox::up-button, QSpinBox::down-button {{
    background: {C_CARD};
    border: none;
    width: 16px;
}}

QCheckBox {{ color: {C_LABEL}; spacing: 8px; }}
QCheckBox::indicator {{
    width: 16px; height: 16px;
    border: 1px solid {C_BORDER};
    border-radius: 3px;
    background: {C_SURFACE};
}}
QCheckBox::indicator:checked {{
    background: {C_ACCENT};
    border-color: {C_ACCENT};
}}
QCheckBox:hover {{ color: {C_TEXT}; }}

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
    background: {C_BG}; width: 6px; border-radius: 3px;
}}
QScrollBar::handle:vertical {{
    background: {C_BORDER}; border-radius: 3px; min-height: 20px;
}}
QScrollBar::handle:vertical:hover {{ background: {C_MUTED}; }}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
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
        headers={"Authorization": f"Bearer {token}", "User-Agent": APP_NAME},
    )
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            status_code = response.status
            body = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"HTTP {exc.code}: {exc.read().decode('utf-8', errors='replace')}") from exc
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
    return {"provider": provider, "room_id": room_id, "encryption_key": encryption_key, "dns_server": dns_server}

def validate_manual_config(provider: str, room_id: str, encryption_key: str, dns_server: str) -> dict:
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
    return {"provider": provider, "room_id": room_id, "encryption_key": encryption_key, "dns_server": dns_server}

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
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
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
            p.setBrush(glow)
            p.setPen(Qt.NoPen)
            p.drawEllipse(0, 0, 14, 14)
        p.setBrush(color)
        p.setPen(Qt.NoPen)
        p.drawEllipse(3, 3, 8, 8)


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
        self.setStyleSheet(f"color: {C_BORDER}; background: {C_BORDER}; max-height: 1px;")


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
        self.setStyleSheet(STYLESHEET + f"""
            QDialog {{ background: {C_BG}; border: 1px solid {C_BORDER}; border-radius: 12px; }}
        """)
        s = settings

        self.auto_fetch_config_checkbox = QCheckBox("Получать конфиг автоматически с сервера")
        self.auto_fetch_config_checkbox.setChecked(bool(s.get("auto_fetch_config", DEFAULT_AUTO_FETCH_CONFIG)))
        self.config_url_input = QLineEdit(s.get("config_url", DEFAULT_CONFIG_URL))
        self.config_token_input = QLineEdit(s.get("config_token", DEFAULT_CONFIG_TOKEN))
        self.config_token_input.setEchoMode(QLineEdit.Password)
        self.provider_input = QLineEdit(s.get("provider", DEFAULT_PROVIDER))
        self.room_id_input = QLineEdit(s.get("room_id", DEFAULT_ROOM_ID))
        self.encryption_key_input = QLineEdit(s.get("encryption_key", DEFAULT_ENCRYPTION_KEY))
        self.encryption_key_input.setEchoMode(QLineEdit.Password)
        self.dns_input = QLineEdit(s.get("dns_server", DEFAULT_DNS_SERVER))
        self.socks_host_input = QLineEdit(s.get("socks_host", DEFAULT_SOCKS_HOST))
        self.socks_port_input = QSpinBox()
        self.socks_port_input.setRange(1, 65535)
        self.socks_port_input.setValue(int(s.get("socks_port", DEFAULT_SOCKS_PORT)))
        self.network_service_input = QLineEdit(s.get("network_service", DEFAULT_NETWORK_SERVICE))
        self.auto_connect_checkbox = QCheckBox("Подключаться автоматически при запуске")
        self.auto_connect_checkbox.setChecked(bool(s.get("auto_connect", False)))
        self.auto_refresh_checkbox = QCheckBox("Автообновление комнаты каждые 5 минут")
        self.auto_refresh_checkbox.setChecked(bool(s.get("auto_refresh", True)))

        layout = QVBoxLayout(self)
        layout.setSpacing(16)
        layout.setContentsMargins(24, 24, 24, 24)

        title = QLabel("НАСТРОЙКИ")
        title.setStyleSheet(f"color: {C_MUTED}; font-size: 10px; letter-spacing: 2px;")
        layout.addWidget(title)

        layout.addWidget(self._section("ИСТОЧНИК КОНФИГУРАЦИИ"))
        layout.addWidget(self.auto_fetch_config_checkbox)
        layout.addLayout(self._row("URL конфига", self.config_url_input))
        layout.addLayout(self._row("Токен", self.config_token_input))
        layout.addWidget(Divider())

        layout.addWidget(self._section("ПОДКЛЮЧЕНИЕ (вручную)"))
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
        layout.addWidget(self.auto_refresh_checkbox)

        close_btn = QPushButton("Сохранить и закрыть")
        close_btn.setMinimumHeight(38)
        close_btn.clicked.connect(self.accept)
        layout.addSpacing(4)
        layout.addWidget(close_btn)

        for w in [self.config_url_input, self.config_token_input,
                  self.provider_input, self.room_id_input,
                  self.encryption_key_input, self.dns_input,
                  self.socks_host_input, self.network_service_input]:
            w.textChanged.connect(self.auto_save_to_parent)
        self.socks_port_input.valueChanged.connect(self.auto_save_to_parent)
        for cb in [self.auto_connect_checkbox, self.auto_refresh_checkbox, self.auto_fetch_config_checkbox]:
            cb.stateChanged.connect(self.auto_save_to_parent)
        self.auto_fetch_config_checkbox.stateChanged.connect(self.update_manual_fields_state)
        self.update_manual_fields_state()

    def _section(self, text: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setStyleSheet(f"color: {C_MUTED}; font-size: 10px; letter-spacing: 1.5px; margin-top: 4px;")
        return lbl

    def _row(self, label: str, widget: QWidget) -> QHBoxLayout:
        lbl = QLabel(label)
        lbl.setFixedWidth(150)
        lbl.setStyleSheet(f"color: {C_LABEL}; font-size: 11px;")
        row = QHBoxLayout()
        row.setSpacing(12)
        row.addWidget(lbl)
        row.addWidget(widget)
        return row

    def auto_save_to_parent(self):
        parent = self.parent()
        if parent is None or not hasattr(parent, "settings") or not hasattr(parent, "save_settings"):
            return
        parent.settings = self.values()
        parent.save_settings()
        if hasattr(parent, "update_state"):
            parent.update_state()

    def update_manual_fields_state(self):
        auto = self.auto_fetch_config_checkbox.isChecked()
        self.config_url_input.setEnabled(auto)
        self.config_token_input.setEnabled(auto)
        self.provider_input.setEnabled(not auto)
        self.room_id_input.setEnabled(not auto)
        self.encryption_key_input.setEnabled(not auto)

    def values(self) -> dict:
        return {
            "auto_fetch_config": self.auto_fetch_config_checkbox.isChecked(),
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
            "auto_refresh": self.auto_refresh_checkbox.isChecked(),
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
            args, stdout=log_file, stderr=subprocess.STDOUT, text=True, bufsize=1
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
        # ── Корневой layout: фиксированная верхняя часть + растягиваемый лог
        root_layout = QVBoxLayout(root)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        # ── ВЕРХНЯЯ ЧАСТЬ (не растягивается, не двигается) ──────────────
        top_widget = QWidget()
        top_layout = QVBoxLayout(top_widget)
        top_layout.setContentsMargins(20, 20, 20, 14)
        top_layout.setSpacing(14)

        # Шапка
        header = QHBoxLayout()
        logo_lbl = QLabel("●  BareBone")
        logo_lbl.setStyleSheet(
            f"color: {C_ACCENT}; font-size: 18px; font-weight: 700; letter-spacing: 2px;"
        )
        self._provider_tag = TagLabel("wbstream")
        self._mode_tag = TagLabel("manual", C_MUTED)
        header.addWidget(logo_lbl)
        header.addSpacing(10)
        header.addWidget(self._provider_tag)
        header.addWidget(self._mode_tag)
        header.addStretch()

        settings_btn = QPushButton("⚙")
        settings_btn.setFixedSize(32, 32)
        settings_btn.setToolTip("Настройки")
        settings_btn.setStyleSheet(
            f"background: {C_CARD}; border: 1px solid {C_BORDER}; "
            f"border-radius: 6px; color: {C_LABEL}; font-size: 14px; padding: 0;"
        )
        settings_btn.clicked.connect(self.open_settings)
        header.addWidget(settings_btn)
        top_layout.addLayout(header)

        # Статус-карточка
        status_card = Card()
        status_card.setFixedHeight(110)
        sc_layout = QVBoxLayout(status_card)
        sc_layout.setContentsMargins(20, 16, 20, 16)
        sc_layout.setSpacing(6)

        row1 = QHBoxLayout()
        self._orb = StatusOrb()
        self._status_label = QLabel("ВЫКЛЮЧЕНО")
        self._status_label.setStyleSheet(
            f"color: {C_TEXT}; font-size: 20px; font-weight: 700; letter-spacing: 2px;"
        )
        row1.addWidget(self._orb, alignment=Qt.AlignVCenter)
        row1.addSpacing(8)
        row1.addWidget(self._status_label, alignment=Qt.AlignVCenter)
        row1.addStretch()
        sc_layout.addLayout(row1)

        self._addr_label = QLabel("SOCKS5  127.0.0.1:8808")
        self._addr_label.setStyleSheet(f"color: {C_MUTED}; font-size: 11px; letter-spacing: 0.5px;")
        sc_layout.addWidget(self._addr_label)

        self._ip_label = QLabel("")
        self._ip_label.setStyleSheet(f"color: {C_ACCENT}; font-size: 11px;")
        sc_layout.addWidget(self._ip_label)
        top_layout.addWidget(status_card)

        # Кнопки: ВКЛЮЧИТЬ / ВЫКЛЮЧИТЬ / Логи ▼
        btn_row = QHBoxLayout()
        btn_row.setSpacing(10)

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

        btn_row.addWidget(self.connect_button, 3)
        btn_row.addWidget(self.disconnect_button, 2)
        btn_row.addWidget(self.logs_button)
        top_layout.addLayout(btn_row)

        root_layout.addWidget(top_widget)   # верхняя часть — НЕ растягивается

        # ── НИЖНЯЯ ЧАСТЬ: лог (скрыт по умолчанию) ─────────────────────
        # Отдельный виджет чтобы его можно было показать/скрыть
        # не трогая верхние кнопки
        log_widget = QWidget()
        log_layout = QVBoxLayout(log_widget)
        log_layout.setContentsMargins(20, 0, 20, 0)
        log_layout.setSpacing(6)

        self.output = QPlainTextEdit()
        self.output.setReadOnly(True)
        self.output.setLineWrapMode(QPlainTextEdit.NoWrap)
        self.output.setMinimumHeight(180)
        log_layout.addWidget(self.output)

        footer = QLabel("BareBone VPN Manager  •  WebRTC tunnel")
        footer.setStyleSheet(f"color: {C_MUTED}; font-size: 10px; letter-spacing: 0.5px;")
        footer.setAlignment(Qt.AlignCenter)
        log_layout.addWidget(footer)
        log_layout.setContentsMargins(20, 0, 20, 14)

        self._log_widget = log_widget
        self._log_widget.hide()                    # скрыт по умолчанию
        root_layout.addWidget(self._log_widget, 1) # растягивается когда видим

        self.setCentralWidget(root)

        # Сигналы
        self.connect_button.clicked.connect(self.connect_client)
        self.disconnect_button.clicked.connect(self.disconnect_client)
        self.logs_button.clicked.connect(self.toggle_logs)

        self.update_state()
        # Установим начальный размер под верхнюю часть
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
            self._ip_label.setText("")

        mode = "auto" if self.settings.get("auto_fetch_config", False) else "manual"
        provider = self.settings.get("provider", DEFAULT_PROVIDER)
        self._provider_tag.setText(provider)
        self._mode_tag.setText(mode)
        self._addr_label.setText(
            f"SOCKS5  {self.socks_host()}:{self.socks_port()}  "
            f"•  HTTP  {self.socks_host()}:{self.socks_port() + 1}"
        )
        self.connect_button.setEnabled(not running and not self.is_reconnecting)
        self.disconnect_button.setEnabled(running or self.is_reconnecting)

    def _set_status(self, text: str, state: str):
        colors = {"off": C_MUTED, "connecting": C_ACCENT2, "on": C_ACCENT, "error": C_RED}
        color = colors.get(state, C_MUTED)
        self._status_label.setText(text)
        self._status_label.setStyleSheet(
            f"color: {color}; font-size: 20px; font-weight: 700; letter-spacing: 2px;"
        )
        self._orb.set_state(state)

    def toggle_logs(self):
        """Показать/скрыть лог. Верхняя часть НЕ двигается."""
        visible = self._log_widget.isVisible()
        self._log_widget.setVisible(not visible)
        self.logs_button.setText("Логи ▲" if not visible else "Логи ▼")
        # Окно само подгоняет размер — кнопки остаются на месте
        self.adjustSize()

    def append_log(self, text: str):
        if not text:
            return
        self.output.appendPlainText(str(text).rstrip())
        self.output.verticalScrollBar().setValue(self.output.verticalScrollBar().maximum())

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
            "auto_fetch_config": DEFAULT_AUTO_FETCH_CONFIG,
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
            "auto_refresh": True,
        }
        path = get_settings_path()
        if not path.exists():
            return defaults
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            defaults.update(data)
            for k, v in [
                ("config_url", DEFAULT_CONFIG_URL),
                ("config_token", DEFAULT_CONFIG_TOKEN),
                ("provider", DEFAULT_PROVIDER),
                ("dns_server", DEFAULT_DNS_SERVER),
            ]:
                if not defaults.get(k):
                    defaults[k] = v
            return defaults
        except Exception:
            return defaults

    def save_settings(self):
        get_settings_path().write_text(
            json.dumps(self.settings, ensure_ascii=False, indent=2), encoding="utf-8"
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
    # Подключение
    # ----------------------------------------------------------

    def get_connection_config(self) -> dict:
        if self.settings.get("auto_fetch_config", False):
            cfg = fetch_connection_http(
                self.settings.get("config_url", DEFAULT_CONFIG_URL),
                self.settings.get("config_token", DEFAULT_CONFIG_TOKEN),
            )
            self.settings.update({
                "provider": cfg["provider"],
                "room_id": cfg["room_id"],
                "encryption_key": cfg["encryption_key"],
                "dns_server": cfg.get("dns_server", DEFAULT_DNS_SERVER),
            })
            self.save_settings()
            return cfg
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
            "-transport", DEFAULT_TRANSPORT,
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
                ["curl", "--max-time", "5", "--silent", "--show-error",
                 "--socks5-hostname", f"{self.socks_host()}:{self.socks_port()}",
                 "https://ifconfig.me"],
                timeout=8, windows_no_window=True,
            )
            if code == 0 and output.strip():
                ip = output.strip()
                self.append_log(f"Туннель готов. IP выхода: {ip}")
                self._ip_label.setText(f"↳  выход через  {ip}")
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
            self.client_log_file = open(self.client_log_path, "a", encoding="utf-8", buffering=1)
            self.client_log_position = (
                self.client_log_path.stat().st_size if self.client_log_path.exists() else 0
            )
            self.client_process = self.platform.start_process(args, self.client_log_file)
            self.log_timer.start()
            time.sleep(1)

            if self.client_process.poll() is not None:
                raise RuntimeError("BB вышел сразу. Смотри логи.")

            if not self.wait_proxy_ready(timeout_seconds=25):
                raise RuntimeError("Туннель не поднялся за 25 сек. Проверь Room ID и ключ.")

            self.platform.enable_system_proxy(self.socks_host(), self.socks_port(), self.network_service())

            if self.settings.get("auto_refresh", True) and self.settings.get("auto_fetch_config", False):
                self.config_timer.start()
            else:
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
            self._ip_label.setText("")
            self.update_state()
        except Exception as exc:
            self._set_status("ОШИБКА", "error")
            self.append_log(f"Ошибка выключения: {exc}")
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
        if self.is_reconnecting or not self.settings.get("auto_fetch_config", False):
            return
        if not self.is_running():
            return
        try:
            new_cfg = fetch_connection_http(
                self.settings.get("config_url", DEFAULT_CONFIG_URL),
                self.settings.get("config_token", DEFAULT_CONFIG_TOKEN),
            )
            if self.current_config == new_cfg:
                self.append_log("Автопроверка: комната не изменилась.")
                return
            self.append_log("Автопроверка: комната изменилась, переподключаюсь.")
            self.settings.update({
                "provider": new_cfg["provider"],
                "room_id": new_cfg["room_id"],
                "encryption_key": new_cfg["encryption_key"],
                "dns_server": new_cfg.get("dns_server", DEFAULT_DNS_SERVER),
            })
            self.save_settings()
            self.is_reconnecting = True
            self.update_state()
            self.disconnect_client()
            self.current_config = new_cfg
            self.connect_client()
        except Exception as exc:
            self.append_log(f"Ошибка автообновления: {exc}")
        finally:
            self.is_reconnecting = False
            self.update_state()

    def closeEvent(self, event):
        if self.is_running():
            reply = QMessageBox.question(
                self, APP_NAME,
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
    window.show()
    sys.exit(app.exec())