import zmq
import mpv

def start_player():
    context = zmq.Context()
    
    # Port 5559: Listen for Play/Stop commands from the Router or UI
    socket = context.socket(zmq.PULL)
    socket.bind("tcp://127.0.0.1:5559")

    # Initialize the MPV media player
    player = mpv.MPV()
    print("[*] MPV Player Worker started. Listening on Port 5559...")

    while True:
        try:
            message = socket.recv_json()
            action = message.get("action")
            file_path = message.get("file_path")

            if action == "play":
                print(f"\n[>] Play command received for: {file_path}")
                
                # SAFETY CHECK: Only play if the file_path actually exists
                if file_path is not None:
                    player.play(file_path)
                else:
                    print("[!] Warning: Received 'play' command, but the file_path was empty (None). Ignoring.")
            
            elif action == "stop":
                print("\n[■] Stopping playback.")
                player.stop()
                
        except Exception as e:
            print(f"[!] Player Error: {e}")

if __name__ == "__main__":
    start_player()
