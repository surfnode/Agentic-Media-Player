import zmq
import yt_dlp
import os
import sys
from pathlib import Path

# Ensure Python can find our custom modules when running as a standalone script
sys.path.append(str(Path(__file__).resolve().parent.parent.parent))
from agentic_player.core.db_manager import DatabaseManager

# Setup download directory
DOWNLOAD_DIR = Path.home() / "Music" / "AgenticPlayer"
DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)

def start_worker():
    # 1. ZeroMQ Setup
    context = zmq.Context()
    
    # Task Bus (PULL): Where we receive commands from the Agent Router
    pull_socket = context.socket(zmq.PULL)
    pull_socket.bind("tcp://127.0.0.1:5556") # Worker binds here for now
    
    # State Bus (PUB): Where we broadcast progress to the PySide6 UI
    pub_socket = context.socket(zmq.PUB)
    pub_socket.connect("tcp://127.0.0.1:5557") # Connects to the UI's SUB socket
    
    # 2. Database Setup
    db = DatabaseManager()
    
    print(f"[*] Fetcher Worker started. Listening for tasks...")
    print(f"[*] Downloads will save to: {DOWNLOAD_DIR}")

    # 3. The yt-dlp Progress Hook
    def progress_hook(d):
        if d['status'] == 'downloading':
            total = d.get('total_bytes') or d.get('total_bytes_estimate', 0)
            downloaded = d.get('downloaded_bytes', 0)
            if total > 0:
                percent = int((downloaded / total) * 100)
                pub_socket.send_json({"type": "progress", "value": percent})
        elif d['status'] == 'finished':
            pub_socket.send_json({"type": "progress", "value": 100})
            print(f"\n[+] Download finished, processing audio...")

    while True:
        # Wait for a command (Blocks until a message arrives)
        message = pull_socket.recv_json()
        
        if message.get("action") == "download":
            query = message.get("query")
            print(f"\n[*] Received command to download: {query}")
            
            # 4. yt-dlp Configuration
            ydl_opts = {
                'format': 'bestaudio/best',
                'outtmpl': str(DOWNLOAD_DIR / '%(title)s.%(ext)s'),
                'postprocessors': [{
                    'key': 'FFmpegExtractAudio',
                    'preferredcodec': 'mp3',
                    'preferredquality': '192',
                }],
                'progress_hooks': [progress_hook],
                'quiet': True, # Keep terminal output clean
                'noplaylist': True
            }
            
            # 5. Execute Download
            try:
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    # yt-dlp's default behavior searches if a URL isn't provided
                    search_query = f"ytsearch1:{query}" if not query.startswith("http") else query
                    info = ydl.extract_info(search_query, download=True)
                    
                    # If it was a search, extract the first result
                    if 'entries' in info:
                        info = info['entries'][0]
                        
                    title = info.get('title', 'Unknown Title')
                    artist = info.get('uploader', 'Unknown Artist')
                    duration = info.get('duration', 0)
                    
                    # The postprocessor changes the extension to mp3
                    final_filepath = str(DOWNLOAD_DIR / f"{title}.mp3")
                    
                    # 6. Update SQLite
                    db.add_track(title=title, artist=artist, file_path=final_filepath, duration=duration)
                    print(f"[+] Saved '{title}' to Database.")
                    
                    # 7. Tell the UI to refresh
                    pub_socket.send_json({"type": "download_complete"})
                    
            except Exception as e:
                print(f"[!] Download failed: {e}")

if __name__ == "__main__":
    start_worker()
