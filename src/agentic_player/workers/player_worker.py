import os
import zmq
import vlc
import sqlite3
import random
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[2]))
from agentic_player.core.settings import load_settings

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
    
    instance = vlc.Instance('--quiet')
    player = instance.media_player_new()
    
    s = load_settings()
    volume = max(0, min(100, int(s.get("volume", 100))))
    muted = bool(s.get("muted", False))
    player.audio_set_volume(volume)
    player.audio_set_mute(muted)
    print(f"[*] Boot volume: {volume}{' (muted)' if muted else ''}")
    
    current_track_idx = -1
    shuffle_mode = False
    cached_win_id = None
    queue = []  # active play context; empty = fall back to full library

    def play_target(file_path):
        if cached_win_id:
            player.set_xwindow(cached_win_id)
        player.stop()
        player.set_media(instance.media_new(file_path))
        player.audio_set_volume(volume)
        player.audio_set_mute(muted)
        player.play()
        print(f"[*] VLC Playing: {os.path.basename(file_path)}")
        progress_pub.send_json({"type": "track_changed", "file_path": file_path})

    def start_collection(files, start_path=None):
        """Replace the play context with `files` and play start_path (or first)."""
        valid = [f for f in files if f and os.path.exists(f)]
        if not valid:
            print("[!] play_collection: no playable files in that collection.")
            return False
        queue.clear()
        queue.extend(valid)
        if start_path and start_path in queue:
            current_idx = queue.index(start_path)
        else:
            current_idx = 0
        set_current_and_play(current_idx)
        return True

    current_track_idx = -1

    def set_current_and_play(idx):
        nonlocal current_track_idx
        current_track_idx = idx
        play_target(queue[idx])

    while True:
        try:
            socks = dict(poller.poll(200))
            
            if cmd_socket in socks:
                msg = cmd_socket.recv_json()
                action = msg.get("action")
                
                if "win_id" in msg:
                    cached_win_id = msg["win_id"]

                if action == "play":
                    file_path = msg.get("file_path")
                    if file_path and os.path.exists(file_path):
                        # Direct file play (agent): context becomes the full library
                        library = get_playlist()
                        queue.clear()
                        queue.extend(library)
                        if file_path in queue:
                            set_current_and_play(queue.index(file_path))
                        else:
                            queue.clear()
                            queue.append(file_path)
                            set_current_and_play(0)
                    else:
                        current_state = player.get_state()
                        if current_state == vlc.State.Paused:
                            player.play()
                            print("[*] Resumed playback")
                        elif current_state == vlc.State.Playing:
                            print("[*] Audio is already playing.")
                        else:
                            pool = queue if queue else get_playlist()
                            if pool:
                                if shuffle_mode:
                                    set_current_and_play(random.randint(0, len(pool) - 1))
                                else:
                                    set_current_and_play(0)
                            else:
                                print("[!] Play command received, but library is empty.")
                
                elif action == "play_collection":
                    start_collection(msg.get("files") or [], msg.get("start_path"))
                
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
                    pool = queue if queue else get_playlist()
                    if not pool: continue
                    if shuffle_mode:
                        set_current_and_play(random.randint(0, len(pool) - 1))
                    elif current_track_idx < len(pool) - 1:
                        set_current_and_play(current_track_idx + 1)
                    else:
                        set_current_and_play(0)
                        
                elif action == "prev":
                    pool = queue if queue else get_playlist()
                    if not pool: continue
                    if shuffle_mode:
                        set_current_and_play(random.randint(0, len(pool) - 1))
                    elif current_track_idx > 0:
                        set_current_and_play(current_track_idx - 1)
                    else:
                        set_current_and_play(len(pool) - 1)
                    
                elif action == "toggle_shuffle":
                    shuffle_mode = not shuffle_mode
                    print(f"[*] Shuffle Mode: {'ON' if shuffle_mode else 'OFF'}")

                elif action == "seek":
                    pos = msg.get("value", 0.0)
                    player.set_position(pos)

                elif action == "set_volume":
                    volume = max(0, min(100, int(msg.get("value", 100))))
                    player.audio_set_volume(volume)
                    print(f"[*] Volume: {volume}")

                elif action == "set_mute":
                    muted = bool(msg.get("value", False))
                    player.audio_set_mute(muted)
                    print(f"[*] Muted: {muted}")
                        
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
                pool = queue if queue else get_playlist()
                if pool and current_track_idx != -1:
                    if shuffle_mode:
                        set_current_and_play(random.randint(0, len(pool) - 1))
                    elif current_track_idx < len(pool) - 1:
                        set_current_and_play(current_track_idx + 1)
                    else:
                        set_current_and_play(0)

        except Exception as e:
            print(f"[!] VLC Playback Error: {e}")

if __name__ == "__main__":
    start_player_worker()
