import sys
import os

os.environ["QT_QPA_PLATFORM"] = "xcb"

import sqlite3
import zmq
import sounddevice as sd
from PySide6.QtWidgets import (QApplication, QMainWindow, QDockWidget, 
                               QWidget, QVBoxLayout, QHBoxLayout, QTextEdit, QTextBrowser, QLineEdit, 
                               QPushButton, QLabel, QDialog, QFormLayout, QComboBox, 
                               QDialogButtonBox, QCheckBox, QTabWidget, QSlider, QProgressBar)
from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap, QPalette, QColor
from PySide6.QtSql import QSqlDatabase

from agentic_player.core.db_manager import DatabaseManager
from agentic_player.core.settings import load_settings, save_settings
from agentic_player.core.zmq_bridge import ZMQBridge
from agentic_player.ui.library_widget import LibraryWidget

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
    QLabel#stageWidget { background-color: #181825; color: #cdd6f4; font-size: 20px; }
    QLabel#summaryLabel, QLabel#statusLabel { color: #a6adc8; font-size: 11px; margin-bottom: 4px; }
    QLineEdit#searchBar { padding: 5px; border-radius: 4px; background-color: #313244; color: #cdd6f4; border: 1px solid #45475a; }
    QLineEdit, QTextBrowser { background-color: #181825; color: #cdd6f4; border: 1px solid #45475a; padding: 4px; border-radius: 4px; }
    QPushButton { background-color: #313244; color: #cdd6f4; border: 1px solid #45475a; border-radius: 4px; padding: 4px 14px; font-weight: bold; }
    QPushButton:hover { background-color: #45475a; }
    QPushButton:checked { background-color: #89b4fa; color: #1e1e2e; }
    QPushButton#sendButton { background-color: #89b4fa; color: #1e1e2e; }
    QPushButton#sendButton:hover { background-color: #b4befe; }
    QPushButton#muteButton { padding: 4px; font-size: 15px; }
    QPushButton#muteButton:checked { background-color: #f38ba8; color: #1e1e2e; }
    
    QProgressBar#micMeter { border: 1px solid #45475a; border-radius: 4px; background-color: #181825; }
    QProgressBar#micMeter::chunk { background-color: #a6e3a1; width: 4px; margin: 1px; }

    QTreeWidget { background-color: #181825; alternate-background-color: #1e1e2e; border: 1px solid #45475a; border-radius: 4px; }
    QHeaderView::section { background-color: #313244; color: #cdd6f4; padding: 4px; border: 1px solid #45475a; }
    QDockWidget { color: #cdd6f4; font-weight: bold; }
    QDockWidget::title { background: #313244; padding-left: 5px; padding-top: 4px; border-radius: 4px; }
    QComboBox { background-color: #313244; border: 1px solid #45475a; border-radius: 4px; padding: 2px 8px; }
    QComboBox::drop-down { border-left: 1px solid #45475a; }
    QTabWidget::pane { border: 1px solid #45475a; background-color: #181825; border-radius: 4px; }
    QTabBar::tab { background: #313244; color: #cdd6f4; border: 1px solid #45475a; padding: 6px 12px; border-top-left-radius: 4px; border-top-right-radius: 4px; }
    QTabBar::tab:selected { background: #181825; border-bottom-color: #181825; font-weight: bold; }
    
    QSlider::groove:horizontal { border: 1px solid #45475a; height: 6px; background: #1e1e2e; border-radius: 3px; margin: 2px 0; }
    QSlider::sub-page:horizontal { background: #89b4fa; border-radius: 3px; }
    QSlider::handle:horizontal { background: #cdd6f4; border: 1px solid #45475a; width: 14px; margin: -5px 0; border-radius: 7px; }
    QSlider::handle:horizontal:hover { background: #f38ba8; }
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
        
        # --- KOKORO TTS TOOLS ---
        self.kokoro_voice_combo = QComboBox()
        self.kokoro_voice_combo.addItems([
            "af_bella (American Female)",
            "af_sarah (American Female)",
            "af_sky (American Female)",
            "af_nicole (American Female)",
            "am_adam (American Male)",
            "am_michael (American Male)",
            "am_onyx (American Male)",
            "bf_emma (British Female)",
            "bm_george (British Male)"
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

        # --- Prefill from persisted settings ---
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
        self.setWindowTitle("Agentic Media Player")
        self.resize(1240, 820)

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
        
        self.zmq_bridge.download_complete.connect(self.library_widget.refresh_library)
        self.library_widget.play_requested.connect(self.send_play_command)
        self.zmq_bridge.chat_received.connect(self.display_ai_message)
        self.zmq_bridge.progress_updated.connect(self.update_progress)
        self.zmq_bridge.mic_volume_updated.connect(self.update_mic_volume)
        self.zmq_bridge.track_changed.connect(self.on_track_changed)

    def _load_persisted_settings(self):
        """Apply settings.json to the UI at boot. Workers read the same file
        themselves, so nothing is broadcast here (a boot-time PUB would be
        lost anyway - subscribers are still connecting)."""
        s = load_settings()

        # Inference toggles - block signals so we don't broadcast/save mid-boot
        for w in (self.stt_toggle, self.tts_toggle, self.stt_combo, self.tts_combo):
            w.blockSignals(True)
        self.stt_toggle.setChecked(s.get("stt_enabled", True))
        self.tts_toggle.setChecked(s.get("tts_enabled", True))
        self.stt_combo.setCurrentText(s.get("stt_engine", "Qwen3-ASR (1.7B)"))
        self.tts_combo.setCurrentText(s.get("tts_engine", "Kokoro-82M (Fast)"))
        for w in (self.stt_toggle, self.tts_toggle, self.stt_combo, self.tts_combo):
            w.blockSignals(False)

        self.ptt_button.setEnabled(self.stt_toggle.isChecked() and not self.always_on_toggle.isChecked())
        self.always_on_toggle.setEnabled(self.stt_toggle.isChecked())

        # Volume / mute - restored visually; player worker boots from the same file
        self.volume_slider.blockSignals(True)
        self.volume_slider.setValue(int(s.get("volume", 100)))
        self.volume_slider.blockSignals(False)
        self.mute_button.blockSignals(True)
        self.mute_button.setChecked(bool(s.get("muted", False)))
        self.mute_button.setText("🔇" if self.mute_button.isChecked() else "🔊")
        self.mute_button.blockSignals(False)

        mic_name = s.get("mic_name") or "Auto-Detect (System Default)"
        mic_name = mic_name.split("] ")[-1] if "] " in mic_name else mic_name
        self.mic_status_label.setText(f"🎤 In: {mic_name[:25]}")
        spk_name = s.get("spk_name") or "Auto-Detect (System Default)"
        spk_name = spk_name.split("] ")[-1] if "] " in spk_name else spk_name
        self.spk_status_label.setText(f"🔊 Out: {spk_name[:25]}")

    def send_play_command(self, file_path):
        win_id = int(self.central_widget.winId())
        self.cmd_socket.send_json({"action": "play", "file_path": file_path, "win_id": win_id})

    def send_transport_command(self, action):
        win_id = int(self.central_widget.winId())
        self.cmd_socket.send_json({"action": action, "win_id": win_id})

    def on_track_changed(self, file_path):
        if not file_path: return
        is_video = "downloads/video" in file_path.replace('\\', '/')
        if is_video:
            self.central_widget.clear()
        else:
            with sqlite3.connect(self.db_manager.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT thumbnail_path, title FROM tracks WHERE file_path=?", (file_path,))
                result = cursor.fetchone()
                if result and result[0] and os.path.exists(result[0]):
                    pixmap = QPixmap(result[0])
                    self.central_widget.setPixmap(pixmap.scaled(self.central_widget.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation))
                else:
                    title = result[1] if result else os.path.basename(file_path)
                    self.central_widget.clear()
                    self.central_widget.setText(f"🎵 Playing: {title}")

    def on_slider_moved(self, value):
        pos = value / 1000.0
        self.cmd_socket.send_json({"action": "seek", "value": pos})

    def on_volume_changed(self, value):
        self.cmd_socket.send_json({"action": "set_volume", "value": value})

    def on_volume_released(self):
        # Persist once per drag (valueChanged only sends to the player worker)
        save_settings({"volume": self.volume_slider.value()})

    def on_mute_toggled(self, checked):
        self.mute_button.setText("🔇" if checked else "🔊")
        save_settings({"muted": checked})
        self.cmd_socket.send_json({"action": "set_mute", "value": checked})

    def update_progress(self, pos, time_ms, length_ms):
        if not self.slider.isSliderDown() and pos >= 0:
            self.slider.setValue(int(pos * 1000))
        def fmt_time(ms):
            if ms <= 0: return "00:00"
            s = ms // 1000
            m = s // 60
            return f"{m:02d}:{s%60:02d}"
        self.time_label.setText(fmt_time(time_ms))
        self.duration_label.setText(fmt_time(length_ms))

    def update_mic_volume(self, volume):
        val = min(int(volume * 400), 100)
        self.mic_meter.setValue(val)

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
        if checked:
            self.ptt_button.setStyleSheet("background-color: #313244; color: #6c7086; font-weight: bold; border-radius: 22px; border: 2px solid #45475a; font-size: 14px;")
            self.ptt_button.setText("🎙️ Auto-Listening Mode")
        else:
            self.ptt_button.setStyleSheet("background-color: #181825; color: #a6e3a1; font-weight: bold; border-radius: 22px; border: 2px solid #a6e3a1; font-size: 14px;")
            self.ptt_button.setText("🎤 Push to Talk")
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
            self.mic_status_label.setText(f"🎤 In: {mic_disp[:25]}")
            self.spk_status_label.setText(f"🔊 Out: {spk_disp[:25]}")
            
            # Broadcast the full config so live workers hot-swap
            self.config_pub_socket.send_json({"type": "hardware_update", "config": config})
            self.config_pub_socket.send_json({"type": "llm_update", "config": config})

    def closeEvent(self, event):
        # Belt and suspenders: persist final volume state on exit
        save_settings({
            "volume": self.volume_slider.value(),
            "muted": self.mute_button.isChecked(),
        })
        print("[*] Shutting down ZMQ Bridge gracefully...")
        self.zmq_bridge.stop()
        event.accept()

    def _setup_ui(self):
        self.central_widget = QLabel("Stage (Album Art / Audio Visualizer)", alignment=Qt.AlignCenter)
        self.central_widget.setObjectName("stageWidget")
        self.setCentralWidget(self.central_widget)

        left_dock = QDockWidget("Library", self)
        left_dock.setAllowedAreas(Qt.LeftDockWidgetArea | Qt.RightDockWidgetArea)
        self.library_widget = LibraryWidget()
        left_dock.setWidget(self.library_widget)
        self.addDockWidget(Qt.LeftDockWidgetArea, left_dock)

        right_dock = QDockWidget("Agent Terminal", self)
        right_dock.setAllowedAreas(Qt.LeftDockWidgetArea | Qt.RightDockWidgetArea)
        agent_container = QWidget()
        agent_layout = QVBoxLayout(agent_container)
        
        self.chat_history = QTextBrowser()
        self.chat_history.setOpenExternalLinks(True)
        self.chat_history.setReadOnly(True)
        
        input_layout = QHBoxLayout()
        self.text_input = QLineEdit()
        self.text_input.setPlaceholderText("Type a command or ask a music question...")
        self.text_input.returnPressed.connect(self.send_chat_command)
        
        self.send_button = QPushButton("Send")
        self.send_button.setObjectName("sendButton")
        self.send_button.clicked.connect(self.send_chat_command)
        
        input_layout.addWidget(self.text_input)
        input_layout.addWidget(self.send_button)

        toggle_layout = QHBoxLayout()
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
        
        toggle_layout.addWidget(self.stt_toggle)
        toggle_layout.addWidget(self.stt_combo)
        toggle_layout.addWidget(self.tts_toggle)
        toggle_layout.addWidget(self.tts_combo)
        
        bottom_buttons_layout = QHBoxLayout()
        
        ptt_layout = QVBoxLayout()
        ptt_controls = QHBoxLayout()
        
        self.ptt_button = QPushButton("🎤 Push to Talk")
        self.ptt_button.setMinimumHeight(45)
        self.ptt_button.setStyleSheet("background-color: #181825; color: #a6e3a1; font-weight: bold; border-radius: 22px; border: 2px solid #a6e3a1; font-size: 14px;")
        self.ptt_button.pressed.connect(self.start_voice)
        self.ptt_button.released.connect(self.stop_voice)
        
        self.always_on_toggle = QCheckBox("Always On")
        self.always_on_toggle.toggled.connect(self.toggle_always_on)
        
        ptt_controls.addWidget(self.ptt_button)
        ptt_controls.addWidget(self.always_on_toggle)
        
        self.mic_meter = QProgressBar()
        self.mic_meter.setRange(0, 100)
        self.mic_meter.setTextVisible(False)
        self.mic_meter.setFixedHeight(8)
        self.mic_meter.setObjectName("micMeter")
        
        ptt_layout.addLayout(ptt_controls)
        ptt_layout.addWidget(self.mic_meter)

        status_layout = QVBoxLayout()
        self.mic_status_label = QLabel("🎤 In: Auto-Detect")
        self.mic_status_label.setObjectName("statusLabel")
        self.spk_status_label = QLabel("🔊 Out: Auto-Detect")
        self.spk_status_label.setObjectName("statusLabel")
        status_layout.addWidget(self.mic_status_label)
        status_layout.addWidget(self.spk_status_label)
        
        self.settings_button = QPushButton("⚙️")
        self.settings_button.setMinimumHeight(45)
        self.settings_button.setMinimumWidth(45)
        self.settings_button.clicked.connect(self.open_settings)
        
        bottom_buttons_layout.addLayout(ptt_layout)
        bottom_buttons_layout.addLayout(status_layout)
        bottom_buttons_layout.addWidget(self.settings_button)
        
        agent_layout.addWidget(self.chat_history)
        agent_layout.addLayout(input_layout)
        agent_layout.addLayout(toggle_layout)
        agent_layout.addLayout(bottom_buttons_layout)
        right_dock.setWidget(agent_container)
        self.addDockWidget(Qt.RightDockWidgetArea, right_dock)

        bottom_dock = QDockWidget("Transport", self)
        bottom_dock.setAllowedAreas(Qt.BottomDockWidgetArea)
        transport_container = QWidget()
        transport_main_layout = QVBoxLayout(transport_container)
        
        progress_layout = QHBoxLayout()
        self.time_label = QLabel("00:00")
        self.time_label.setFixedWidth(50)
        self.time_label.setAlignment(Qt.AlignCenter)
        self.duration_label = QLabel("00:00")
        self.duration_label.setFixedWidth(50)
        self.duration_label.setAlignment(Qt.AlignCenter)
        self.slider = QSlider(Qt.Horizontal)
        self.slider.setRange(0, 1000)
        self.slider.sliderMoved.connect(self.on_slider_moved)
        
        self.mute_button = QPushButton("🔊")
        self.mute_button.setObjectName("muteButton")
        self.mute_button.setCheckable(True)
        self.mute_button.setFixedSize(44, 30)
        self.mute_button.setToolTip("Mute / Unmute")
        self.mute_button.toggled.connect(self.on_mute_toggled)

        self.volume_slider = QSlider(Qt.Horizontal)
        self.volume_slider.setRange(0, 100)
        self.volume_slider.setMaximumWidth(140)
        self.volume_slider.setToolTip("Volume")
        self.volume_slider.valueChanged.connect(self.on_volume_changed)
        self.volume_slider.sliderReleased.connect(self.on_volume_released)

        progress_layout.addWidget(self.time_label)
        progress_layout.addWidget(self.slider)
        progress_layout.addWidget(self.duration_label)
        progress_layout.addWidget(self.mute_button)
        progress_layout.addWidget(self.volume_slider)
        
        button_layout = QHBoxLayout()
        for label, action in [("🔀 Shuffle", "toggle_shuffle"), ("⏮ Prev", "prev"), ("▶ Play", "play"), ("⏸ Pause", "pause"), ("⏹ Stop", "stop"), ("⏭ Next", "next")]:
            btn = QPushButton(label)
            btn.setMinimumHeight(40)
            btn.clicked.connect(lambda checked=False, a=action: self.send_transport_command(a))
            if label == "🔀 Shuffle": btn.setCheckable(True)
            button_layout.addWidget(btn)

        transport_main_layout.addLayout(progress_layout)
        transport_main_layout.addLayout(button_layout)
        bottom_dock.setWidget(transport_container)
        self.addDockWidget(Qt.BottomDockWidgetArea, bottom_dock)

if __name__ == "__main__":
    app = QApplication(sys.argv)
    apply_dark_theme(app)
    window = AgenticPlayerWindow()
    window.show()
    sys.exit(app.exec())
