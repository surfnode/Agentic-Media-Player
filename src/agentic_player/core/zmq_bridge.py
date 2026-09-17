import zmq
from PySide6.QtCore import Signal, QThread

class ZMQBridge(QThread):
    progress_updated = Signal(int)
    state_changed = Signal(dict)
    download_complete = Signal()
    chat_received = Signal(str)

    def __init__(self):
        super().__init__()
        self._is_running = True

    def run(self):
        context = zmq.Context()
        
        # Listen to Router Chat (Port 5557)
        router_sub = context.socket(zmq.SUB)
        router_sub.connect("tcp://127.0.0.1:5557")
        router_sub.setsockopt_string(zmq.SUBSCRIBE, "")
        
        # Listen to Fetcher Status (Port 5562)
        fetcher_sub = context.socket(zmq.SUB)
        fetcher_sub.connect("tcp://127.0.0.1:5562")
        fetcher_sub.setsockopt_string(zmq.SUBSCRIBE, "")

        poller = zmq.Poller()
        poller.register(router_sub, zmq.POLLIN)
        poller.register(fetcher_sub, zmq.POLLIN)

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
                    
        router_sub.close()
        fetcher_sub.close()
        context.term()

    def stop(self):
        self._is_running = False
        self.wait()
