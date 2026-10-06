import os
import zmq
import vlc
import sqlite3
import random

def get_playlist():
    db_path = "agentic_player.db"
    if not os.path.exists(db_path):
        return []
    with sqlite3.connect(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT file_path FROM tracks ORDER BY id DESC")
        return [row[0] for row in cursor.fetchall() if os.path.exists(row[0])]

def start_player_worker():
    context = zmq.Context()
    cmd_socket = context.socket(zmq.PULL)
    cmd_socket.setsockopt(zmq.LINGER, 0)
    cmd_socket.bind("tcp://127.0.0.1:5559")

    progress_pub = context.socket(zmq.PUB)
    progress_pub.bind("tcp://127.0.0.1:5563")
    
    poller = zmq.Poller()
    poller.register(cmd_socket, zmq.POLLIN)
    
    print("[*] VLC Player Worker started. Listening on Port 5559...")
    
    # CRITICAL FIX: Removed --no-xlib so VLC can attach to the Qt Window
    instance = vlc.Instance('--quiet')
    player = instance.media_player_new()
    
    current_track_idx = -1
    playlist = []
    shuffle_mode = False
    cached_win_id = None

    def play_target(file_path):
        if cached_win_id:
            player.set_xwindow(cached_win_id)
        player.stop()
        player.set_media(instance.media_new(file_path))
        player.play()
        print(f"[*] VLC Playing: {os.path.basename(file_path)}")
        progress_pub.send_json({"type": "track_changed", "file_path": file_path})

    while True:
        try:
            socks = dict(poller.poll(200))
            
            if cmd_socket in socks:
                msg = cmd_socket.recv_json()
                action = msg.get("action")
                playlist = get_playlist()
                
                if "win_id" in msg:
                    cached_win_id = msg["win_id"]
                
                if action == "play":
                    file_path = msg.get("file_path")
                    if file_path and os.path.exists(file_path):
                        if file_path in playlist:
                            current_track_idx = playlist.index(file_path)
                        play_target(file_path)
                    else:
                        current_state = player.get_state()
                        if current_state == vlc.State.Paused:
                            player.play()
                            print("[*] Resumed playback")
                        elif current_state == vlc.State.Playing:
                            print("[*] Audio is already playing.")
                        else:
                            if playlist:
                                if shuffle_mode:
                                    current_track_idx = random.randint(0, len(playlist) - 1)
                                else:
                                    current_track_idx = 0
                                play_target(playlist[current_track_idx])
                            else:
                                print("[!] Play command received, but library is empty.")
                
                elif action == "pause":
                    if player.get_state() == vlc.State.Playing:
                        player.pause()
                        print("[*] Paused playback")
                    else:
                        print("[*] Ignored pause (nothing is currently playing).")
                    
                elif action == "stop":
                    player.stop()
                    print("[*] Stopped playback")
                    
                elif action == "next":
                    if not playlist: continue
                    if shuffle_mode:
                        current_track_idx = random.randint(0, len(playlist) - 1)
                    elif current_track_idx < len(playlist) - 1:
                        current_track_idx += 1
                    else:
                        current_track_idx = 0 
                    play_target(playlist[current_track_idx])
                        
                elif action == "prev":
                    if not playlist: continue
                    if shuffle_mode:
                        current_track_idx = random.randint(0, len(playlist) - 1)
                    elif current_track_idx > 0:
                        current_track_idx -= 1
                    else:
                        current_track_idx = len(playlist) - 1
                    play_target(playlist[current_track_idx])
                    
                elif action == "toggle_shuffle":
                    shuffle_mode = not shuffle_mode
                    print(f"[*] Shuffle Mode: {'ON' if shuffle_mode else 'OFF'}")

                elif action == "seek":
                    pos = msg.get("value", 0.0)
                    player.set_position(pos)

            current_state = player.get_state()
            
            if current_state == vlc.State.Playing:
                time_ms = player.get_time()
                length_ms = player.get_length()
                pos = player.get_position()
                
                progress_pub.send_json({
                    "type": "progress",
                    "time": time_ms,
                    "length": length_ms,
                    "position": pos
                })
                
            elif current_state == vlc.State.Ended:
                playlist = get_playlist()
                if playlist and current_track_idx != -1:
                    if shuffle_mode:
                        current_track_idx = random.randint(0, len(playlist) - 1)
                    elif current_track_idx < len(playlist) - 1:
                        current_track_idx += 1
                    else:
                        current_track_idx = 0
                    play_target(playlist[current_track_idx])

        except Exception as e:
            print(f"[!] VLC Playback Error: {e}")

if __name__ == "__main__":
    start_player_worker()
