import sys
import os

os.environ["QT_QPA_PLATFORM"] = "xcb"

import sqlite3
import zmq
import sounddevice as sd
from PySide6.QtWidgets import (QApplication, QMainWindow, QDockWidget, QWidget, QVBoxLayout,
                                QHBoxLayout, QTextEdit, QTextBrowser, QLineEdit, QPushButton, QLabel,
                                QDialog, QFormLayout, QComboBox, QDialogButtonBox, QCheckBox,
                                QTabWidget, QSlider, QProgressBar, QStackedWidget, QButtonGroup,
                                QSizePolicy, QMenu, QInputDialog, QMessageBox)
from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap, QPalette, QColor
from PySide6.QtSql import QSqlDatabase

from agentic_player.core.db_manager import DatabaseManager
from agentic_player.core.settings import load_settings, save_settings
from agentic_player.core.zmq_bridge import ZMQBridge
from agentic_player.ui.pages import (HomePage, LibraryPage, GenresPage, PlaylistsPage,
                                     NowPlayingPage, TrackCard)

def init_qt_db(db_path="agentic_player.db"):
    db = QSqlDatabase.addDatabase("QSQLITE")
    db.setDatabaseName(db_path)
    if not db.open():
        print(f"Failed to open Qt Database: {db.lastError().text()}")
        sys.exit(1)

def apply_dark_theme(app):
    app.setStyle("Fusion")
    dark_palette = QPalette()
    dark_palette.setColor(QPalette.Window, QColor("#1e1e2e"))
    dark_palette.setColor(QPalette.WindowText, QColor("#cdd6f4"))
    dark_palette.setColor(QPalette.Base, QColor("#181825"))
    dark_palette.setColor(QPalette.AlternateBase, QColor("#1e1e2e"))
    dark_palette.setColor(QPalette.ToolTipBase, QColor("#313244"))
    dark_palette.setColor(QPalette.ToolTipText, QColor("#cdd6f4"))
    dark_palette.setColor(QPalette.Text, QColor("#cdd6f4"))
    dark_palette.setColor(QPalette.Button, QColor("#313244"))
    dark_palette.setColor(QPalette.ButtonText, QColor("#cdd6f4"))
    dark_palette.setColor(QPalette.BrightText, QColor("#f38ba8"))
    dark_palette.setColor(QPalette.Link, QColor("#89b4fa"))
    dark_palette.setColor(QPalette.Highlight, QColor("#89b4fa"))
    dark_palette.setColor(QPalette.HighlightedText, QColor("#1e1e2e"))
    app.setPalette(dark_palette)

    qss = """
    QWidget { font-size: 13px; }
    QLabel#logoTile {
        background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #f38ba8, stop:0.55 #cba6f7, stop:1 #89b4fa);
        color: #11111b; border-radius: 8px; font-size: 15px; font-weight: 900;
    }
    QLabel#brandWord { font-size: 17px; font-weight: 800; color: #cdd6f4; }
    QLabel#statusChip { background: #313244; border: 1px solid #45475a; border-radius: 15px; }
    QPushButton#settingsButton { border: none; background: transparent; font-size: 17px; }
    QPushButton#settingsButton:hover { background: #313244; border-radius: 8px; }
    QLabel#sectionHeader { font-size: 15px; font-weight: bold; }
    QLabel#nowTitle { font-size: 18px; font-weight: bold; }
    QLabel#summaryLabel, QLabel#statusLabel { color: #a6adc8; font-size: 11px; }
    QLabel#cardTitle { font-weight: bold; }
    QLabel#cardSub { color: #a6adc8; font-size: 11px; }

    #topBar { background: #181825; border-bottom: 1px solid #45475a; }
    #sidebar { background: #181825; border-right: 1px solid #45475a; }
    #miniPlayer { background: #181825; border-top: 1px solid #45475a; }
    #stageVideo { background: #000; }
    #stageArt { background: #181825; color: #cdd6f4; font-size: 40px; }

    QPushButton#navButton { text-align: left; padding: 9px 14px; border: none; border-radius: 8px; background: transparent; color: #cdd6f4; }
    QPushButton#navButton:hover { background: #313244; }
    QPushButton#navButton:checked { background: #313244; color: #89b4fa; font-weight: bold; }

    QLineEdit#globalSearch { padding: 7px 12px; border-radius: 16px; background: #313244; color: #cdd6f4; border: 1px solid #45475a; }
    QLineEdit, QTextBrowser { background: #181825; color: #cdd6f4; border: 1px solid #45475a; padding: 4px; border-radius: 4px; }
    QPushButton { background: #313244; color: #cdd6f4; border: 1px solid #45475a; border-radius: 4px; padding: 4px 14px; font-weight: bold; }
    QPushButton:hover { background: #45475a; }
    QPushButton:checked { background: #89b4fa; color: #1e1e2e; }
    QPushButton#sendButton { background: #89b4fa; color: #1e1e2e; }
    QPushButton#sendButton:hover { background: #b4befe; }
    QPushButton#muteButton { padding: 4px; font-size: 15px; }
    QPushButton#muteButton:checked { background: #f38ba8; color: #1e1e2e; }
    QPushButton#playButton { min-width: 52px; font-size: 16px; }

    QProgressBar#micMeter { border: 1px solid #45475a; border-radius: 4px; background: #181825; }
    QProgressBar#micMeter::chunk { background: #a6e3a1; width: 4px; margin: 1px; }

    QTreeWidget, QListWidget { background: #181825; alternate-background-color: #1e1e2e; border: 1px solid #45475a; border-radius: 4px; }
    QHeaderView::section { background: #313244; color: #cdd6f4; padding: 4px; border: 1px solid #45475a; }
    QDockWidget { color: #cdd6f4; font-weight: bold; }
    QDockWidget::title { background: #313244; padding-left: 5px; padding-top: 4px; border-radius: 4px; }
    QComboBox { background: #313244; border: 1px solid #45475a; border-radius: 4px; padding: 2px 8px; }
    QComboBox::drop-down { border-left: 1px solid #45475a; }
    QTabWidget::pane { border: 1px solid #45475a; background: #181825; border-radius: 4px; }
    QTabBar::tab { background: #313244; color: #cdd6f4; border: 1px solid #45475a; padding: 6px 12px; border-top-left-radius: 4px; border-top-right-radius: 4px; }
    QTabBar::tab:selected { background: #181825; border-bottom-color: #181825; font-weight: bold; }

    QSlider::groove:horizontal { border: 1px solid #45475a; height: 6px; background: #1e1e2e; border-radius: 3px; margin: 2px 0; }
    QSlider::sub-page:horizontal { background: #89b4fa; border-radius: 3px; }
    QSlider::handle:horizontal { background: #cdd6f4; border: 1px solid #45475a; width: 14px; margin: -5px 0; border-radius: 7px; }
    QSlider::handle:horizontal:hover { background: #f38ba8; }

    QScrollArea { border: none; }
    """
    app.setStyleSheet(qss)

class SettingsDialog(QDialog):
    def __init__(self, current=None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Application Settings")
        self.setMinimumWidth(500)
        self.setMinimumHeight(450)
        main_layout = QVBoxLayout(self)
        self.tabs = QTabWidget()

        hw_tab = QWidget()
        hw_layout = QFormLayout(hw_tab)
        self.mic_combo = QComboBox()
        self.spk_combo = QComboBox()
        self.mic_combo.addItem("Auto-Detect (System Default)", None)
        self.spk_combo.addItem("Auto-Detect (System Default)", None)
        devices = sd.query_devices()
        for i, dev in enumerate(devices):
            if dev['max_input_channels'] > 0:
                self.mic_combo.addItem(f"[{i}] {dev['name']}", i)
            if dev['max_output_channels'] > 0:
                self.spk_combo.addItem(f"[{i}] {dev['name']}", i)
        hw_layout.addRow("Microphone Input:", self.mic_combo)
        hw_layout.addRow("Speaker Output:", self.spk_combo)

        ai_tab = QWidget()
        ai_layout = QFormLayout(ai_tab)
        self.llm_model_combo = QComboBox()
        self.llm_model_combo.setEditable(True)
        self.llm_model_combo.addItems([
            "ollama/granite4.2:8b-q8_0", "ollama/llama3.1", "ollama/mistral", "ollama/qwen2.5"
        ])
        self.llm_api_input = QLineEdit("http://localhost:11434")
        self.search_shows_check = QCheckBox("Enable Web Search & Links (Music Shows)")
        self.search_shows_check.setChecked(True)
        self.kokoro_voice_combo = QComboBox()
        self.kokoro_voice_combo.addItems([
            "af_bella (American Female)", "af_sarah (American Female)",
            "af_sky (American Female)", "af_nicole (American Female)",
            "am_adam (American Male)", "am_michael (American Male)",
            "am_onyx (American Male)", "bf_emma (British Female)", "bm_george (British Male)"
        ])
        self.kokoro_speed = QSlider(Qt.Horizontal)
        self.kokoro_speed.setRange(50, 150)
        self.kokoro_speed.setValue(100)
        self.kokoro_speed.setTickPosition(QSlider.TicksBelow)
        self.kokoro_speed.setTickInterval(10)
        ai_layout.addRow("LLM Model:", self.llm_model_combo)
        ai_layout.addRow("Ollama API URL:", self.llm_api_input)
        ai_layout.addRow("", self.search_shows_check)
        ai_layout.addRow(QLabel("--- Text-to-Speech ---"))
        ai_layout.addRow("Kokoro Voice:", self.kokoro_voice_combo)
        ai_layout.addRow("Kokoro Speed (50%-150%):", self.kokoro_speed)

        ui_tab = QWidget()
        ui_layout = QFormLayout(ui_tab)
        self.theme_combo = QComboBox()
        self.theme_combo.addItems(["Catppuccin Mocha (Dark)", "Light Mode"])
        ui_layout.addRow("Theme:", self.theme_combo)

        self.tabs.addTab(hw_tab, "🎧 Hardware")
        self.tabs.addTab(ai_tab, "🧠 AI Models & TTS")
        self.tabs.addTab(ui_tab, "🎨 Appearance")

        current = current or {}
        for combo, key in [(self.mic_combo, "mic_name"), (self.spk_combo, "spk_name")]:
            idx = combo.findText(current.get(key) or "")
            if idx >= 0:
                combo.setCurrentIndex(idx)
        self.llm_model_combo.setCurrentText(current.get("llm_model") or "ollama/granite4.2:8b-q8_0")
        self.llm_api_input.setText(current.get("llm_api") or "http://localhost:11434")
        self.search_shows_check.setChecked(current.get("web_search_enabled", True))
        voice_id = current.get("kokoro_voice") or "af_bella"
        vidx = self.kokoro_voice_combo.findText(voice_id, Qt.MatchStartsWith)
        if vidx >= 0:
            self.kokoro_voice_combo.setCurrentIndex(vidx)
        self.kokoro_speed.setValue(int(round(float(current.get("kokoro_speed", 1.0)) * 100)))

        main_layout.addWidget(self.tabs)
        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        main_layout.addWidget(buttons)

    def get_all_settings(self):
        return {
            "mic_device_id": self.mic_combo.currentData(),
            "mic_name": self.mic_combo.currentText(),
            "spk_device_id": self.spk_combo.currentData(),
            "spk_name": self.spk_combo.currentText(),
            "llm_model": self.llm_model_combo.currentText(),
            "llm_api": self.llm_api_input.text(),
            "web_search_enabled": self.search_shows_check.isChecked(),
            "kokoro_voice": self.kokoro_voice_combo.currentText().split(" ")[0],
            "kokoro_speed": self.kokoro_speed.value() / 100.0
        }

class AgenticPlayerWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Agentic Player")
        self.resize(1280, 860)

        self.zmq_context = zmq.Context()
        self.cmd_socket = self.zmq_context.socket(zmq.PUSH)
        self.cmd_socket.connect("tcp://127.0.0.1:5559")
        self.agent_socket = self.zmq_context.socket(zmq.PUSH)
        self.agent_socket.connect("tcp://127.0.0.1:5555")
        self.voice_socket = self.zmq_context.socket(zmq.PUSH)
        self.voice_socket.connect("tcp://127.0.0.1:5560")
        self.config_pub_socket = self.zmq_context.socket(zmq.PUB)
        self.config_pub_socket.bind("tcp://127.0.0.1:5561")

        self.db_manager = DatabaseManager()
        init_qt_db()

        self.zmq_bridge = ZMQBridge()
        self.zmq_bridge.start()

        self._setup_ui()
        self._load_persisted_settings()

        self.zmq_bridge.download_complete.connect(self.on_library_changed)
        self.zmq_bridge.chat_received.connect(self.display_ai_message)
        self.zmq_bridge.progress_updated.connect(self.update_progress)
        self.zmq_bridge.mic_volume_updated.connect(self.update_mic_volume)
        self.zmq_bridge.track_changed.connect(self.on_track_changed)
        self.zmq_bridge.state_changed.connect(self.on_player_state)

    # ---------------- UI construction ----------------

    def _setup_ui(self):
        shell = QWidget()
        root = QVBoxLayout(shell)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # Top bar
        top = QWidget()
        top.setObjectName("topBar")
        top.setFixedHeight(56)
        tl = QHBoxLayout(top)
        tl.setContentsMargins(16, 8, 16, 8)
        tl.setSpacing(12)

        # Logo: gradient play tile + two-tone wordmark
        logo_tile = QLabel("▶")
        logo_tile.setObjectName("logoTile")
        logo_tile.setFixedSize(30, 30)
        logo_tile.setAlignment(Qt.AlignCenter)
        wordmark = QLabel('Agentic<span style="color:#f38ba8;">Player</span>')
        wordmark.setObjectName("brandWord")
        brand_row = QHBoxLayout()
        brand_row.setSpacing(9)
        brand_row.addWidget(logo_tile)
        brand_row.addWidget(wordmark)
        tl.addLayout(brand_row)

        tl.addStretch()

        self.search_box = QLineEdit()
        self.search_box.setObjectName("globalSearch")
        self.search_box.setPlaceholderText("🔍 Search your library…")
        self.search_box.setClearButtonEnabled(True)
        self.search_box.setMinimumWidth(280)
        self.search_box.setMaximumWidth(480)
        self.search_box.textChanged.connect(self.on_search_changed)
        tl.addWidget(self.search_box)

        tl.addStretch()

        # Compact device chips - full names live in tooltips, so the bar
        # never gets crowded (this was the overlap culprit)
        self.mic_status_label = QLabel("🎤")
        self.mic_status_label.setObjectName("statusChip")
        self.mic_status_label.setFixedSize(30, 30)
        self.mic_status_label.setAlignment(Qt.AlignCenter)
        self.mic_status_label.setToolTip("Microphone: Auto-Detect (System Default)")
        self.spk_status_label = QLabel("🔊")
        self.spk_status_label.setObjectName("statusChip")
        self.spk_status_label.setFixedSize(30, 30)
        self.spk_status_label.setAlignment(Qt.AlignCenter)
        self.spk_status_label.setToolTip("Speaker: Auto-Detect (System Default)")
        self.settings_button = QPushButton("⚙️")
        self.settings_button.setObjectName("settingsButton")
        self.settings_button.setFixedSize(34, 34)
        self.settings_button.setToolTip("Settings")
        self.settings_button.clicked.connect(self.open_settings)
        tl.addWidget(self.mic_status_label)
        tl.addWidget(self.spk_status_label)
        tl.addWidget(self.settings_button)
        root.addWidget(top)

        # Middle: sidebar + page stack
        middle = QHBoxLayout()
        middle.setContentsMargins(0, 0, 0, 0)
        middle.setSpacing(0)

        sidebar = QWidget()
        sidebar.setObjectName("sidebar")
        sidebar.setFixedWidth(200)
        sl = QVBoxLayout(sidebar)
        sl.setContentsMargins(8, 12, 8, 12)
        self.nav_group = QButtonGroup(self)
        self.nav_group.setExclusive(True)
        self.pages = QStackedWidget()

        self.home_page = HomePage(self.db_manager)
        self.library_page = LibraryPage(self.db_manager)
        self.genres_page = GenresPage(self.db_manager)
        self.playlists_page = PlaylistsPage(self.db_manager)
        self.now_playing_page = NowPlayingPage()

        page_specs = [
            ("🏠  Home", self.home_page),
            ("🗂  Library", self.library_page),
            ("🎸  Genres", self.genres_page),
            ("📃  Playlists", self.playlists_page),
            ("▶  Now Playing", self.now_playing_page),
        ]
        for label, page in page_specs:
            self.pages.addWidget(page)
            btn = QPushButton(label)
            btn.setObjectName("navButton")
            btn.setCheckable(True)
            btn.clicked.connect(lambda checked=False, i=self.pages.indexOf(page): self.pages.setCurrentIndex(i))
            self.nav_group.addButton(btn)
            sl.addWidget(btn)

        sl.addStretch()
        self.agent_toggle = QPushButton("🤖  Agent")
        self.agent_toggle.setObjectName("navButton")
        self.agent_toggle.setCheckable(True)
        self.agent_toggle.setChecked(True)
        self.agent_toggle.clicked.connect(lambda checked: self.agent_dock.setVisible(checked))
        sl.addWidget(self.agent_toggle)

        middle.addWidget(sidebar)
        middle.addWidget(self.pages, 1)
        root.addLayout(middle, 1)

        # Mini player
        mini = QWidget()
        mini.setObjectName("miniPlayer")
        mini.setFixedHeight(76)
        ml = QHBoxLayout(mini)
        ml.setContentsMargins(16, 8, 16, 8)
        ml.setSpacing(12)

        self.now_thumb = QLabel("🎵")
        self.now_thumb.setFixedSize(56, 56)
        self.now_thumb.setAlignment(Qt.AlignCenter)
        self.now_thumb.setStyleSheet("background: #313244; border-radius: 6px; font-size: 22px;")
        ml.addWidget(self.now_thumb)

        info = QVBoxLayout()
        self.now_title = QLabel("Nothing playing")
        self.now_title.setObjectName("cardTitle")
        self.now_artist = QLabel("")
        self.now_artist.setObjectName("cardSub")
        info.addWidget(self.now_title)
        info.addWidget(self.now_artist)
        ml.addLayout(info)
        ml.addStretch()

        self.prev_button = QPushButton("⏮")
        self.prev_button.clicked.connect(lambda: self.send_transport_command("prev"))
        self.play_button = QPushButton("▶")
        self.play_button.setObjectName("playButton")
        self.play_button.clicked.connect(self.on_play_clicked)
        self.next_button = QPushButton("⏭")
        self.next_button.clicked.connect(lambda: self.send_transport_command("next"))
        self.stop_button = QPushButton("⏹")
        self.stop_button.clicked.connect(lambda: self.send_transport_command("stop"))
        for b in (self.prev_button, self.play_button, self.next_button, self.stop_button):
            ml.addWidget(b)

        ml.addStretch()
        self.time_label = QLabel("00:00")
        self.time_label.setFixedWidth(48)
        self.time_label.setAlignment(Qt.AlignCenter)
        self.duration_label = QLabel("00:00")
        self.duration_label.setFixedWidth(48)
        self.duration_label.setAlignment(Qt.AlignCenter)
        self.seek_slider = QSlider(Qt.Horizontal)
        self.seek_slider.setRange(0, 1000)
        self.seek_slider.sliderMoved.connect(self.on_slider_moved)
        ml.addWidget(self.time_label)
        ml.addWidget(self.seek_slider, 2)
        ml.addWidget(self.duration_label)

        self.mute_button = QPushButton("🔊")
        self.mute_button.setObjectName("muteButton")
        self.mute_button.setCheckable(True)
        self.mute_button.setFixedSize(44, 30)
        self.mute_button.toggled.connect(self.on_mute_toggled)
        self.volume_slider = QSlider(Qt.Horizontal)
        self.volume_slider.setRange(0, 100)
        self.volume_slider.setMaximumWidth(120)
        self.volume_slider.valueChanged.connect(self.on_volume_changed)
        self.volume_slider.sliderReleased.connect(self.on_volume_released)
        ml.addWidget(self.mute_button)
        ml.addWidget(self.volume_slider)
        root.addWidget(mini)

        self.setCentralWidget(shell)

        # Pages -> player
        for page in (self.home_page, self.library_page, self.genres_page):
            page.play_requested.connect(self.send_play_collection_command)
        self.playlists_page.play_requested.connect(self.send_play_collection_command)
        self.genres_page.menu_requested.connect(self.on_card_menu)
        self.playlists_page.menu_requested.connect(self.on_playlist_card_menu)

        # Agent dock
        self.agent_dock = QDockWidget("🤖 Agent", self)
        self.agent_dock.setAllowedAreas(Qt.LeftDockWidgetArea | Qt.RightDockWidgetArea)
        agent_container = QWidget()
        al = QVBoxLayout(agent_container)

        self.chat_history = QTextBrowser()
        self.chat_history.setOpenExternalLinks(True)
        self.chat_history.setReadOnly(True)
        al.addWidget(self.chat_history, 1)

        input_row = QHBoxLayout()
        self.text_input = QLineEdit()
        self.text_input.setPlaceholderText("Ask anything, or say: play / skip / shuffle…")
        self.text_input.returnPressed.connect(self.send_chat_command)
        self.send_button = QPushButton("Send")
        self.send_button.setObjectName("sendButton")
        self.send_button.clicked.connect(self.send_chat_command)
        input_row.addWidget(self.text_input)
        input_row.addWidget(self.send_button)
        al.addLayout(input_row)

        toggle_row = QHBoxLayout()
        self.stt_toggle = QCheckBox("STT:")
        self.stt_toggle.setChecked(True)
        self.stt_toggle.toggled.connect(self.on_inference_toggled)
        self.stt_combo = QComboBox()
        self.stt_combo.addItems(["Qwen3-ASR (1.7B)"])
        self.stt_combo.currentIndexChanged.connect(self.on_inference_toggled)
        self.tts_toggle = QCheckBox("TTS:")
        self.tts_toggle.setChecked(True)
        self.tts_toggle.toggled.connect(self.on_inference_toggled)
        self.tts_combo = QComboBox()
        self.tts_combo.addItems(["Kokoro-82M (Fast)"])
        self.tts_combo.currentIndexChanged.connect(self.on_inference_toggled)
        for w in (self.stt_toggle, self.stt_combo, self.tts_toggle, self.tts_combo):
            toggle_row.addWidget(w)
        toggle_row.addStretch()
        self.always_on_toggle = QCheckBox("Always On")
        self.always_on_toggle.toggled.connect(self.toggle_always_on)
        toggle_row.addWidget(self.always_on_toggle)
        al.addLayout(toggle_row)

        ptt_row = QHBoxLayout()
        self.ptt_button = QPushButton("🎤 Push to Talk")
        self.ptt_button.setMinimumHeight(45)
        self.ptt_button.setStyleSheet("background-color: #181825; color: #a6e3a1; font-weight: bold; border-radius: 22px; border: 2px solid #a6e3a1; font-size: 14px;")
        self.ptt_button.pressed.connect(self.start_voice)
        self.ptt_button.released.connect(self.stop_voice)
        ptt_row.addWidget(self.ptt_button, 1)
        al.addLayout(ptt_row)

        self.mic_meter = QProgressBar()
        self.mic_meter.setRange(0, 100)
        self.mic_meter.setTextVisible(False)
        self.mic_meter.setFixedHeight(8)
        self.mic_meter.setObjectName("micMeter")
        al.addWidget(self.mic_meter)

        self.agent_dock.setWidget(agent_container)
        self.addDockWidget(Qt.RightDockWidgetArea, self.agent_dock)
        self.agent_dock.visibilityChanged.connect(self.agent_toggle.setChecked)

        self.pages.setCurrentIndex(0)
        self.nav_group.buttons()[0].setChecked(True)

    # ---------------- settings / persistence ----------------

    def _load_persisted_settings(self):
        s = load_settings()
        for w in (self.stt_toggle, self.tts_toggle, self.stt_combo, self.tts_combo):
            w.blockSignals(True)
        self.stt_toggle.setChecked(s.get("stt_enabled", True))
        self.tts_toggle.setChecked(s.get("tts_enabled", True))
        self.stt_combo.setCurrentText(s.get("stt_engine", "Qwen3-ASR (1.7B)"))
        self.tts_combo.setCurrentText(s.get("tts_engine", "Kokoro-82M (Fast)"))
        for w in (self.stt_toggle, self.tts_toggle, self.stt_combo, self.tts_combo):
            w.blockSignals(False)

        self.volume_slider.blockSignals(True)
        self.volume_slider.setValue(int(s.get("volume", 100)))
        self.volume_slider.blockSignals(False)
        self.mute_button.blockSignals(True)
        self.mute_button.setChecked(bool(s.get("muted", False)))
        self.mute_button.setText("🔇" if self.mute_button.isChecked() else "🔊")
        self.mute_button.blockSignals(False)

        self.ptt_button.setEnabled(self.stt_toggle.isChecked() and not self.always_on_toggle.isChecked())
        self.always_on_toggle.setEnabled(self.stt_toggle.isChecked())

        mic_name = s.get("mic_name") or "Auto-Detect (System Default)"
        mic_name = mic_name.split("] ")[-1] if "] " in mic_name else mic_name
        self.mic_status_label.setToolTip(f"Microphone: {mic_name}")
        spk_name = s.get("spk_name") or "Auto-Detect (System Default)"
        spk_name = spk_name.split("] ")[-1] if "] " in spk_name else spk_name
        self.spk_status_label.setToolTip(f"Speaker: {spk_name}")

    # ---------------- playback plumbing ----------------

    def send_transport_command(self, action):
        self.cmd_socket.send_json({"action": action})

    def send_play_collection_command(self, files, start_path):
        """Clicking any card/tree item: jump to Now Playing (YT watch-page
        behavior) and hand the player the collection as its play context."""
        self.pages.setCurrentWidget(self.now_playing_page)
        self.now_playing_page.set_queue(files, start_path)
        win_id = int(self.now_playing_page.video_surface.winId())
        self.cmd_socket.send_json({
            "action": "play_collection",
            "files": list(files),
            "start_path": start_path,
            "win_id": win_id,
        })

    def on_play_clicked(self):
        if self.play_button.text() == "⏸":
            self.send_transport_command("pause")
        else:
            self.send_transport_command("play")

    def on_player_state(self, msg):
        state = msg.get("state", "stopped")
        self.play_button.setText("⏸" if state == "playing" else "▶")

    def on_track_changed(self, file_path):
        if not file_path:
            return
        is_video = "downloads/video" in file_path.replace("\\", "/")
        title, artist, thumb = os.path.basename(file_path), "", None
        with sqlite3.connect(self.db_manager.db_path) as conn:
            row = conn.execute(
                "SELECT title, artist, thumbnail_path FROM tracks WHERE file_path=?",
                (file_path,)).fetchone()
            if row:
                title, artist, thumb = row[0] or title, row[1] or "", row[2]
        self.now_title.setText(title)
        self.now_artist.setText(artist or "Unknown Artist")
        if is_video:
            self.pages.setCurrentWidget(self.now_playing_page)
        self.now_playing_page.set_track(title, artist, thumb, is_video, file_path)

    def on_library_changed(self):
        self.home_page.refresh()
        self.library_page.refresh()
        self.genres_page.refresh()
        self.playlists_page.refresh()

    def on_search_changed(self, text):
        page = self.pages.currentWidget()
        if hasattr(page, "set_filter"):
            page.set_filter(text)

    # ---------------- card context menus ----------------

    def on_card_menu(self, payload):
        card, pos = payload if isinstance(payload, tuple) else (payload, None)
        m = QMenu(self)
        add_menu = m.addMenu("➕ Add to playlist")
        for pid, name, count in self.db_manager.get_playlists():
            add_menu.addAction(f"{name} ({count})", lambda checked=False, pid=pid, c=card:
                                (self.db_manager.add_track_to_playlist(pid, c.t_id),
                                 self.playlists_page.refresh()))
        add_menu.addSeparator()
        add_menu.addAction("✨ New playlist…", lambda c=card: self._new_playlist_with([c.t_id]))
        m.addSeparator()
        m.addAction("🎸 Set genre…", lambda c=card: self._set_genre([c]))
        m.exec(pos)

    def on_playlist_card_menu(self, payload):
        card, section, pos = payload
        m = QMenu(self)
        add_menu = m.addMenu("➕ Add to playlist")
        for pid, name, count in self.db_manager.get_playlists():
            if pid == section.pid:
                continue
            add_menu.addAction(f"{name} ({count})", lambda checked=False, pid=pid, c=card:
                                (self.db_manager.add_track_to_playlist(pid, c.t_id),
                                 self.playlists_page.refresh()))
        add_menu.addSeparator()
        add_menu.addAction("✨ New playlist…", lambda c=card: self._new_playlist_with([c.t_id]))
        m.addSeparator()
        m.addAction("➖ Remove from this playlist", lambda c=card, s=section:
                    (self.db_manager.remove_track_from_playlist(s.pid, c.t_id),
                     self.playlists_page.refresh()))
        m.addAction("🎸 Set genre…", lambda c=card: self._set_genre([c]))
        m.exec(pos)

    def _new_playlist_with(self, t_ids):
        name, ok = QInputDialog.getText(self, "New playlist", "Playlist name:")
        if not (ok and name.strip()):
            return
        pid = self.db_manager.create_playlist(name)
        if pid is None:
            QMessageBox.warning(self, "New playlist", f"'{name}' already exists.")
            return
        for t in t_ids:
            self.db_manager.add_track_to_playlist(pid, t)
        self.playlists_page.refresh()

    def _set_genre(self, cards):
        for c in cards:
            text, ok = QInputDialog.getText(self, "Set genre", f"Genre for '{c.title}':", text=c.genre or "")
            if not ok:
                return
            self.db_manager.set_track_genre(c.t_id, text.strip())
            self.genres_page.refresh()

    # ---------------- transport / sliders ----------------

    def on_slider_moved(self, value):
        self.cmd_socket.send_json({"action": "seek", "value": value / 1000.0})

    def on_volume_changed(self, value):
        self.cmd_socket.send_json({"action": "set_volume", "value": value})

    def on_volume_released(self):
        save_settings({"volume": self.volume_slider.value()})

    def on_mute_toggled(self, checked):
        self.mute_button.setText("🔇" if checked else "🔊")
        save_settings({"muted": checked})
        self.cmd_socket.send_json({"action": "set_mute", "value": checked})

    def update_progress(self, pos, time_ms, length_ms):
        if not self.seek_slider.isSliderDown() and pos >= 0:
            self.seek_slider.setValue(int(pos * 1000))
        def fmt_time(ms):
            if ms <= 0: return "00:00"
            s = ms // 1000
            m = s // 60
            return f"{m:02d}:{s%60:02d}"
        self.time_label.setText(fmt_time(time_ms))
        self.duration_label.setText(fmt_time(length_ms))

    def update_mic_volume(self, volume):
        self.mic_meter.setValue(min(int(volume * 400), 100))

    # ---------------- agent / voice ----------------

    def send_chat_command(self):
        user_text = self.text_input.text().strip()
        if not user_text: return
        self.chat_history.append(f"<b>You:</b> {user_text}")
        self.text_input.clear()
        self.agent_socket.send_json({"type": "chat", "text": user_text})

    def display_ai_message(self, text):
        self.chat_history.append(f"<b style='color:#f38ba8;'>Agent:</b> {text}<br>")

    def start_voice(self):
        if not self.stt_toggle.isChecked() or self.always_on_toggle.isChecked(): return
        self.ptt_button.setStyleSheet("background-color: #f38ba8; color: #1e1e2e; font-weight: bold; border-radius: 22px; border: 2px solid #f38ba8; font-size: 14px;")
        self.ptt_button.setText("🎙️ Listening...")
        self.voice_socket.send_json({"action": "start"})

    def stop_voice(self):
        if not self.stt_toggle.isChecked() or self.always_on_toggle.isChecked(): return
        self.ptt_button.setStyleSheet("background-color: #181825; color: #a6e3a1; font-weight: bold; border-radius: 22px; border: 2px solid #a6e3a1; font-size: 14px;")
        self.ptt_button.setText("🎤 Push to Talk")
        self.voice_socket.send_json({"action": "stop"})

    def toggle_always_on(self, checked):
        self.ptt_button.setEnabled(not checked)
        if not checked:
            self.ptt_button.setStyleSheet("background-color: #181825; color: #a6e3a1; font-weight: bold; border-radius: 22px; border: 2px solid #a6e3a1; font-size: 14px;")
        else:
            self.ptt_button.setStyleSheet("background-color: #313244; color: #6c7086; font-weight: bold; border-radius: 22px; border: 2px solid #45475a; font-size: 14px;")
        self.voice_socket.send_json({"action": "toggle_always_on", "value": checked})

    def on_inference_toggled(self):
        stt_active = self.stt_toggle.isChecked()
        tts_active = self.tts_toggle.isChecked()
        self.ptt_button.setEnabled(stt_active and not self.always_on_toggle.isChecked())
        self.always_on_toggle.setEnabled(stt_active)
        save_settings({
            "stt_enabled": stt_active,
            "tts_enabled": tts_active,
            "stt_engine": self.stt_combo.currentText(),
            "tts_engine": self.tts_combo.currentText(),
        })
        self.config_pub_socket.send_json({
            "type": "inference_toggle",
            "config": {
                "stt_enabled": stt_active,
                "tts_enabled": tts_active,
                "stt_engine": self.stt_combo.currentText(),
                "tts_engine": self.tts_combo.currentText()
            }
        })

    def open_settings(self):
        dialog = SettingsDialog(current=load_settings(), parent=self)
        if dialog.exec() == QDialog.Accepted:
            config = dialog.get_all_settings()
            save_settings(config)
            mic_disp = config["mic_name"].split("] ")[-1] if "] " in config["mic_name"] else config["mic_name"]
            spk_disp = config["spk_name"].split("] ")[-1] if "] " in config["spk_name"] else config["spk_name"]
            self.mic_status_label.setToolTip(f"Microphone: {mic_disp}")
            self.spk_status_label.setToolTip(f"Speaker: {spk_disp}")
            self.config_pub_socket.send_json({"type": "hardware_update", "config": config})
            self.config_pub_socket.send_json({"type": "llm_update", "config": config})

    def closeEvent(self, event):
        save_settings({
            "volume": self.volume_slider.value(),
            "muted": self.mute_button.isChecked(),
        })
        print("[*] Shutting down ZMQ Bridge gracefully...")
        self.zmq_bridge.stop()
        event.accept()

if __name__ == "__main__":
    app = QApplication(sys.argv)
    apply_dark_theme(app)
    window = AgenticPlayerWindow()
    window.show()
    sys.exit(app.exec())
