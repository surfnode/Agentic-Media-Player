import sys
import zmq
import sounddevice as sd
from PySide6.QtWidgets import (QApplication, QMainWindow, QDockWidget, 
                               QWidget, QVBoxLayout, QHBoxLayout, QTextEdit, QLineEdit, 
                               QPushButton, QLabel, QDialog, QFormLayout, QComboBox, 
                               QDialogButtonBox, QCheckBox)
from PySide6.QtCore import Qt
from PySide6.QtSql import QSqlDatabase

from agentic_player.core.db_manager import DatabaseManager
from agentic_player.core.zmq_bridge import ZMQBridge
from agentic_player.ui.library_widget import LibraryWidget

def init_qt_db(db_path="agentic_player.db"):
    db = QSqlDatabase.addDatabase("QSQLITE")
    db.setDatabaseName(db_path)
    if not db.open():
        print(f"Failed to open Qt Database: {db.lastError().text()}")
        sys.exit(1)

class SettingsDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Hardware Settings")
        self.setMinimumWidth(450)
        
        layout = QFormLayout(self)
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
                
        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        
        layout.addRow("Microphone (Whisper STT):", self.mic_combo)
        layout.addRow("Speaker (Bark TTS):", self.spk_combo)
        layout.addWidget(buttons)
        
    def get_selected_devices(self):
        return {
            "mic_device_id": self.mic_combo.currentData(),
            "mic_name": self.mic_combo.currentText(),
            "spk_device_id": self.spk_combo.currentData(),
            "spk_name": self.spk_combo.currentText()
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
        
        self.zmq_bridge.download_complete.connect(self.library_widget.refresh_library)
        self.library_widget.play_requested.connect(self.send_play_command)
        self.zmq_bridge.chat_received.connect(self.display_ai_message)

    def send_play_command(self, file_path):
        self.cmd_socket.send_json({"action": "play", "file_path": file_path})

    def send_transport_command(self, action):
        self.cmd_socket.send_json({"action": action})

    def send_chat_command(self):
        user_text = self.text_input.text().strip()
        if not user_text: return
        self.chat_history.append(f"<b>You:</b> {user_text}")
        self.text_input.clear()
        self.agent_socket.send_json({"type": "chat", "text": user_text})

    def display_ai_message(self, text):
        self.chat_history.append(f"<b style='color:#f38ba8;'>Agent:</b> {text}<br>")

    def start_voice(self):
        if not self.stt_toggle.isChecked():
            return
        self.ptt_button.setStyleSheet("background-color: #f38ba8; color: white; font-weight: bold;")
        self.ptt_button.setText("🎙️ Listening...")
        self.voice_socket.send_json({"action": "start"})
        
    def stop_voice(self):
        self.ptt_button.setStyleSheet("background-color: #f38ba8; color: black; font-weight: bold;")
        self.ptt_button.setText("🎤 Push to Talk")
        self.voice_socket.send_json({"action": "stop"})

    def on_inference_toggled(self):
        stt_active = self.stt_toggle.isChecked()
        tts_active = self.tts_toggle.isChecked()
        self.ptt_button.setEnabled(stt_active)
        self.config_pub_socket.send_json({
            "type": "inference_toggle",
            "config": {"stt_enabled": stt_active, "tts_enabled": tts_active}
        })

    def open_settings(self):
        dialog = SettingsDialog(self)
        if dialog.exec() == QDialog.Accepted:
            config = dialog.get_selected_devices()
            mic_disp = config["mic_name"].split("] ")[-1] if "] " in config["mic_name"] else config["mic_name"]
            spk_disp = config["spk_name"].split("] ")[-1] if "] " in config["spk_name"] else config["spk_name"]
            self.mic_status_label.setText(f"🎤 In: {mic_disp[:25]}")
            self.spk_status_label.setText(f"🔊 Out: {spk_disp[:25]}")
            self.config_pub_socket.send_json({"type": "hardware_update", "config": config})

    def _setup_ui(self):
        self.central_widget = QLabel("Stage (Album Art / Audio Visualizer)", alignment=Qt.AlignCenter)
        self.central_widget.setStyleSheet("background-color: #1e1e2e; color: #cdd6f4; font-size: 20px;")
        self.setCentralWidget(self.central_widget)

        # Left Dock: Library
        left_dock = QDockWidget("Library", self)
        left_dock.setAllowedAreas(Qt.LeftDockWidgetArea | Qt.RightDockWidgetArea)
        self.library_widget = LibraryWidget()
        left_dock.setWidget(self.library_widget)
        self.addDockWidget(Qt.LeftDockWidgetArea, left_dock)

        # Right Dock: Agent Terminal
        right_dock = QDockWidget("Agent Terminal", self)
        right_dock.setAllowedAreas(Qt.LeftDockWidgetArea | Qt.RightDockWidgetArea)
        agent_container = QWidget()
        agent_layout = QVBoxLayout(agent_container)
        
        self.chat_history = QTextEdit()
        self.chat_history.setReadOnly(True)
        
        input_layout = QHBoxLayout()
        self.text_input = QLineEdit()
        self.text_input.setPlaceholderText("Type a command or ask a music question...")
        self.text_input.returnPressed.connect(self.send_chat_command)
        
        self.send_button = QPushButton("Send")
        self.send_button.setStyleSheet("background-color: #89b4fa; color: black; font-weight: bold; padding: 4px 12px;")
        self.send_button.clicked.connect(self.send_chat_command)
        
        input_layout.addWidget(self.text_input)
        input_layout.addWidget(self.send_button)

        # Inference Toggles
        toggle_layout = QHBoxLayout()
        self.stt_toggle = QCheckBox("Voice Input (Whisper)")
        self.stt_toggle.setChecked(True)
        self.stt_toggle.toggled.connect(self.on_inference_toggled)
        
        self.tts_toggle = QCheckBox("Voice Output (Bark)")
        self.tts_toggle.setChecked(True)
        self.tts_toggle.toggled.connect(self.on_inference_toggled)
        
        toggle_layout.addWidget(self.stt_toggle)
        toggle_layout.addWidget(self.tts_toggle)
        
        # Bottom Mic & Settings
        bottom_buttons_layout = QHBoxLayout()
        self.ptt_button = QPushButton("🎤 Push to Talk")
        self.ptt_button.setMinimumHeight(45)
        self.ptt_button.setStyleSheet("background-color: #f38ba8; color: black; font-weight: bold;")
        self.ptt_button.pressed.connect(self.start_voice)
        self.ptt_button.released.connect(self.stop_voice)
        
        status_layout = QVBoxLayout()
        self.mic_status_label = QLabel("🎤 In: Auto-Detect (System Default)")
        self.mic_status_label.setStyleSheet("color: #a6adc8; font-size: 11px;")
        self.spk_status_label = QLabel("🔊 Out: Auto-Detect (System Default)")
        self.spk_status_label.setStyleSheet("color: #a6adc8; font-size: 11px;")
        status_layout.addWidget(self.mic_status_label)
        status_layout.addWidget(self.spk_status_label)
        
        self.settings_button = QPushButton("⚙️")
        self.settings_button.setMinimumHeight(45)
        self.settings_button.setMinimumWidth(45)
        self.settings_button.clicked.connect(self.open_settings)
        
        bottom_buttons_layout.addWidget(self.ptt_button)
        bottom_buttons_layout.addLayout(status_layout)
        bottom_buttons_layout.addWidget(self.settings_button)
        
        agent_layout.addWidget(self.chat_history)
        agent_layout.addLayout(input_layout)
        agent_layout.addLayout(toggle_layout)
        agent_layout.addLayout(bottom_buttons_layout)
        right_dock.setWidget(agent_container)
        self.addDockWidget(Qt.RightDockWidgetArea, right_dock)

        # Bottom Dock: Transport Media Controls
        bottom_dock = QDockWidget("Transport", self)
        bottom_dock.setAllowedAreas(Qt.BottomDockWidgetArea)
        transport_container = QWidget()
        transport_layout = QHBoxLayout(transport_container)
        
        btn_prev = QPushButton("⏮ Previous")
        btn_prev.clicked.connect(lambda: self.send_transport_command("prev"))
        btn_play = QPushButton("▶ Play")
        btn_play.clicked.connect(lambda: self.send_transport_command("play"))
        btn_pause = QPushButton("⏸ Pause")
        btn_pause.clicked.connect(lambda: self.send_transport_command("pause"))
        btn_stop = QPushButton("⏹ Stop")
        btn_stop.clicked.connect(lambda: self.send_transport_command("stop"))
        btn_next = QPushButton("⏭ Next")
        btn_next.clicked.connect(lambda: self.send_transport_command("next"))

        for btn in (btn_prev, btn_play, btn_pause, btn_stop, btn_next):
            btn.setMinimumHeight(40)
            btn.setStyleSheet("font-weight: bold; padding: 4px 14px;")
            transport_layout.addWidget(btn)

        bottom_dock.setWidget(transport_container)
        self.addDockWidget(Qt.BottomDockWidgetArea, bottom_dock)

if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setStyle("Fusion") 
    window = AgenticPlayerWindow()
    window.show()
    sys.exit(app.exec())
