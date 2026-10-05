import os
import zmq
import yt_dlp
import sqlite3

def init_directories():
    os.makedirs("downloads", exist_ok=True)

def sync_downloads():
    """Scans the downloads folder and injects/updates media files in the database with metadata."""
    db_path = "agentic_player.db"
    if not os.path.exists(db_path):
        return
        
    valid_media_exts = {'.mp4', '.m4a', '.mp3', '.webm', '.ogg', '.wav', '.flac'}
    valid_thumb_exts = {'.webp', '.jpg', '.png', '.jpeg'}
    
    # Attempt to load tinytag for ID3 reading; fallback gracefully if not installed
    try:
        from tinytag import TinyTag
        has_tinytag = True
    except ImportError:
        has_tinytag = False
    
    with sqlite3.connect(db_path) as conn:
        cursor = conn.cursor()
        
        added_or_updated = 0
        for filename in os.listdir("downloads"):
            file_path = os.path.join("downloads", filename)
            if not os.path.isfile(file_path):
                continue
                
            base_name, ext = os.path.splitext(filename)
            ext = ext.lower()
            
            if ext in valid_media_exts:
                thumb_path = ""
                for thumb_ext in valid_thumb_exts:
                    potential_thumb = os.path.join("downloads", base_name + thumb_ext)
                    if os.path.exists(potential_thumb):
                        thumb_path = potential_thumb
                        break
                        
                artist = "Unknown Artist"
                title = base_name.replace("_", " ").strip()

                # 1. Try reading real metadata tags
                if has_tinytag:
                    try:
                        tag = TinyTag.get(file_path)
                        if tag.artist: artist = tag.artist.strip()
                        if tag.title: title = tag.title.strip()
                    except Exception:
                        pass
                        
                # 2. Fallback heuristic: Parse YouTube-style "Artist - Song" filenames
                if artist == "Unknown Artist" and " - " in base_name:
                    parts = base_name.split(" - ", 1)
                    artist = parts[0].strip()
                    title = parts[1].strip()
                elif artist == "Unknown Artist" and "-" in base_name:
                    parts = base_name.split("-", 1)
                    artist = parts[0].strip()
                    title = parts[1].strip()
                    
                # UPSERT logic overwrites existing "Unknown Artist" entries without breaking IDs
                cursor.execute("""
                    INSERT INTO tracks (title, artist, file_path, thumbnail_path)
                    VALUES (?, ?, ?, ?)
                    ON CONFLICT(file_path) DO UPDATE SET
                        title=excluded.title,
                        artist=excluded.artist,
                        thumbnail_path=excluded.thumbnail_path
                """, (title, artist, file_path, thumb_path))
                
                added_or_updated += 1
                
        if added_or_updated > 0:
            conn.commit()
            print(f"[*] Categorized and synced {added_or_updated} local files.")

def start_fetcher_worker():
    init_directories()
    sync_downloads()
    
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
                            
                            try:
                                base_path = os.path.splitext(ydl.prepare_filename(entry))[0]
                            except Exception:
                                continue
                            
                            file_path = ""
                            for ext in ['.mp4', '.m4a', '.mp3', '.webm', '.ogg', '.wav', '.flac']:
                                if os.path.exists(base_path + ext):
                                    file_path = base_path + ext
                                    break
                            
                            thumb_path = ""
                            for ext in ['.webp', '.jpg', '.png', '.jpeg']:
                                if os.path.exists(base_path + ext):
                                    thumb_path = base_path + ext
                                    break
                            
                            if file_path:
                                cursor.execute("""
                                    INSERT INTO tracks (title, artist, file_path, thumbnail_path)
                                    VALUES (?, ?, ?, ?)
                                    ON CONFLICT(file_path) DO UPDATE SET
                                        title=excluded.title,
                                        artist=excluded.artist,
                                        thumbnail_path=excluded.thumbnail_path
                                """, (title, artist, file_path, thumb_path))
                                print(f"[*] Logged {media_type} to DB: {title}")
                        conn.commit()

                # Safety sweep to capture files that evaded strict yt-dlp string matching
                sync_downloads()
                        
                ui_pub.send_json({"type": "download_complete"})
                
        except Exception as e:
            print(f"[!] Fetcher Error: {e}")

if __name__ == "__main__":
    start_fetcher_worker()
