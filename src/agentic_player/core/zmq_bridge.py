import zmq
from PySide6.QtCore import Signal, QThread


class ZMQBridge(QThread):
    progress_updated = Signal(float, int, int)
    mic_volume_updated = Signal(float)
    state_changed = Signal(dict)
    download_complete = Signal()
    chat_received = Signal(str)
    track_changed = Signal(str)

    def __init__(self):
        super().__init__()
        self._is_running = True

    def run(self):
        context = zmq.Context()

        router_sub = context.socket(zmq.SUB)
        router_sub.connect("tcp://127.0.0.1:5557")
        router_sub.setsockopt_string(zmq.SUBSCRIBE, "")

        fetcher_sub = context.socket(zmq.SUB)
        fetcher_sub.connect("tcp://127.0.0.1:5562")
        fetcher_sub.setsockopt_string(zmq.SUBSCRIBE, "")

        progress_sub = context.socket(zmq.SUB)
        progress_sub.connect("tcp://127.0.0.1:5563")
        progress_sub.setsockopt_string(zmq.SUBSCRIBE, "")

        voice_sub = context.socket(zmq.SUB)
        voice_sub.connect("tcp://127.0.0.1:5564")
        voice_sub.setsockopt_string(zmq.SUBSCRIBE, "")

        poller = zmq.Poller()
        poller.register(router_sub, zmq.POLLIN)
        poller.register(fetcher_sub, zmq.POLLIN)
        poller.register(progress_sub, zmq.POLLIN)
        poller.register(voice_sub, zmq.POLLIN)

        while self._is_running:
            socks = dict(poller.poll(100))

            if router_sub in socks:
                try:
                    message = router_sub.recv_json(flags=zmq.NOBLOCK)
                    msg_type = message.get('type')
                    if msg_type == 'chat_reply':
                        self.chat_received.emit(message.get('value', ''))
                except zmq.Again:
                    pass

            if fetcher_sub in socks:
                try:
                    message = fetcher_sub.recv_json(flags=zmq.NOBLOCK)
                    msg_type = message.get('type')
                    if msg_type == 'download_complete':
                        self.download_complete.emit()
                except zmq.Again:
                    pass

            if progress_sub in socks:
                try:
                    message = progress_sub.recv_json(flags=zmq.NOBLOCK)
                    msg_type = message.get('type')
                    if msg_type == 'progress':
                        self.progress_updated.emit(
                            message.get('position', 0.0),
                            message.get('time', 0),
                            message.get('length', 0)
                        )
                    elif msg_type == 'track_changed':
                        self.track_changed.emit(message.get('file_path', ''))
                    elif msg_type == 'state':
                        self.state_changed.emit(message)
                except zmq.Again:
                    pass

            if voice_sub in socks:
                try:
                    message = voice_sub.recv_json(flags=zmq.NOBLOCK)
                    if message.get('type') == 'mic_volume':
                        self.mic_volume_updated.emit(message.get('value', 0.0))
                except zmq.Again:
                    pass

        router_sub.close()
        fetcher_sub.close()
        progress_sub.close()
        voice_sub.close()
        context.term()

    def stop(self):
        self._is_running = False
        self.wait()
