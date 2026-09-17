import os
import zmq
import yt_dlp
import sqlite3

def init_directories():
    os.makedirs("downloads", exist_ok=True)

def start_fetcher_worker():
    init_directories()
    context = zmq.Context()
    
    fetch_socket = context.socket(zmq.PULL)
    fetch_socket.bind("tcp://127.0.0.1:5556")
    
    ui_pub = context.socket(zmq.PUB)
    ui_pub.bind("tcp://127.0.0.1:5562")
    
    print("[*] Fetcher Worker ready. Listening for commands...")
    
    while True:
        try:
            msg = fetch_socket.recv_json()
            action = msg.get("action")
            query = msg.get("query")
            media_type = msg.get("media_type", "video")
            
            if action == "download" and query:
                print(f"\n[*] Initiating {media_type.upper()} Download for: {query}")
                
                # Bypass the bot block without cookies using the Safari client spoof
                extractor_args = {'youtube': ['player_client=web_safari']}
                
                if media_type == "audio":
                    ydl_opts = {
                        'format': 'bestaudio/best',
                        'postprocessors': [{
                            'key': 'FFmpegExtractAudio',
                            'preferredcodec': 'm4a',
                            'preferredquality': '192',
                        }],
                        'extractor_args': extractor_args,
                        'writethumbnail': True,
                        'outtmpl': 'downloads/%(title)s.%(ext)s',
                        'noplaylist': False,
                        'quiet': True,
                        'no_warnings': True,
                        'ignoreerrors': True
                    }
                else:
                    ydl_opts = {
                        'format': 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best',
                        'extractor_args': extractor_args,
                        'writethumbnail': True,
                        'outtmpl': 'downloads/%(title)s.%(ext)s',
                        'noplaylist': False,
                        'quiet': True,
                        'no_warnings': True,
                        'ignoreerrors': True
                    }
                
                search_query = query if query.startswith("http") else f"ytsearch1:{query}"
                
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    info = ydl.extract_info(search_query, download=True)
                    if not info: continue

                    entries = [e for e in info['entries'] if e is not None] if 'entries' in info else [info]
                    
                    with sqlite3.connect("agentic_player.db") as conn:
                        cursor = conn.cursor()
                        for entry in entries:
                            title = entry.get('title', 'Unknown Title')
                            artist = entry.get('uploader', 'Unknown Artist')
                            
                            base_path = os.path.splitext(ydl.prepare_filename(entry))[0]
                            
                            file_path = ""
                            for ext in ['.mp4', '.m4a', '.mp3', '.webm', '.ogg']:
                                if os.path.exists(base_path + ext):
                                    file_path = base_path + ext
                                    break
                            
                            thumb_path = ""
                            for ext in ['.webp', '.jpg', '.png']:
                                if os.path.exists(base_path + ext):
                                    thumb_path = base_path + ext
                                    break
                            
                            if file_path:
                                cursor.execute("""
                                    INSERT OR IGNORE INTO tracks (title, artist, file_path, thumbnail_path)
                                    VALUES (?, ?, ?, ?)
                                """, (title, artist, file_path, thumb_path))
                                print(f"[*] Logged {media_type} to DB: {title}")
                        conn.commit()
                        
                ui_pub.send_json({"type": "download_complete"})
                
        except Exception as e:
            print(f"[!] Fetcher Error: {e}")

if __name__ == "__main__":
    start_fetcher_worker()
