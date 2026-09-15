import zmq
from PySide6.QtCore import Signal, QThread

class ZMQBridge(QThread):
    progress_updated = Signal(int)
    state_changed = Signal(dict)
    download_complete = Signal()
    chat_received = Signal(str) # For receiving AI text

    def run(self):
        context = zmq.Context()
        socket = context.socket(zmq.SUB)
        socket.connect("tcp://127.0.0.1:5557")
        socket.setsockopt_string(zmq.SUBSCRIBE, "")

        while True:
            try:
                message = socket.recv_json(flags=zmq.NOBLOCK)
                msg_type = message.get('type')
                
                if msg_type == 'download_complete':
                    self.download_complete.emit()
                elif msg_type == 'progress':
                    self.progress_updated.emit(message.get('value', 0))
                elif msg_type == 'chat_reply':
                    self.chat_received.emit(message.get('value', ''))
            except zmq.Again:
                self.msleep(100)
