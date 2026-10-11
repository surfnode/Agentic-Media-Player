import os
import zmq
import yt_dlp
import sqlite3
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[2]))
from agentic_player.core.db_manager import DatabaseManager
from agentic_player.core.settings import load_settings


def init_directories():
    os.makedirs("downloads/audio", exist_ok=True)
    os.makedirs("downloads/video", exist_ok=True)


def sync_downloads():
    db_path = "agentic_player.db"
    if not os.path.exists(db_path):
        return

    valid_media_exts = {'.mp4', '.m4a', '.mp3', '.webm', '.ogg', '.wav', '.flac'}
    valid_thumb_exts = {'.webp', '.jpg', '.png', '.jpeg'}

    try:
        from tinytag import TinyTag
        has_tinytag = True
    except ImportError:
        has_tinytag = False

    with sqlite3.connect(db_path) as conn:
        cursor = conn.cursor()
        added_or_updated = 0

        for folder in ["downloads/audio", "downloads/video"]:
            if not os.path.exists(folder):
                continue

            for filename in os.listdir(folder):
                file_path = os.path.join(folder, filename)
                if not os.path.isfile(file_path):
                    continue

                base_name, ext = os.path.splitext(filename)
                ext = ext.lower()

                if ext in valid_media_exts:
                    thumb_path = ""
                    for thumb_ext in valid_thumb_exts:
                        potential_thumb = os.path.join(folder, base_name + thumb_ext)
                        if os.path.exists(potential_thumb):
                            thumb_path = potential_thumb
                            break

                    artist = "Unknown Artist"
                    title = base_name.replace("_", " ").strip()
                    genre = None
                    duration = None

                    if has_tinytag:
                        try:
                            tag = TinyTag.get(file_path)
                            if tag.artist:
                                artist = tag.artist.strip()
                            if tag.title:
                                title = tag.title.strip()
                            genre = (tag.genre or "").strip() or None
                            duration = int(tag.duration) if tag.duration else None
                        except Exception:
                            pass

                    if artist == "Unknown Artist" and " - " in base_name:
                        parts = base_name.split(" - ", 1)
                        artist = parts[0].strip()
                        title = parts[1].strip()
                    elif artist == "Unknown Artist" and "-" in base_name:
                        parts = base_name.split("-", 1)
                        artist = parts[0].strip()
                        title = parts[1].strip()

                    cursor.execute("""
                        INSERT INTO tracks (title, artist, file_path, thumbnail_path, genre, duration)
                        VALUES (?, ?, ?, ?, ?, ?)
                        ON CONFLICT(file_path) DO UPDATE SET
                            title=excluded.title,
                            artist=excluded.artist,
                            thumbnail_path=excluded.thumbnail_path,
                            duration=excluded.duration
                    """, (title, artist, file_path, thumb_path, genre, duration))

                    added_or_updated += 1

        if added_or_updated > 0:
            conn.commit()
            print(f"[*] Categorized and synced {added_or_updated} local files.")


def start_fetcher_worker():
    init_directories()
    DatabaseManager()  # ensure schema exists before raw SQL below
    sync_downloads()

    context = zmq.Context()
    fetch_socket = context.socket(zmq.PULL)
    fetch_socket.bind("tcp://127.0.0.1:5556")
    ui_pub = context.socket(zmq.PUB)
    ui_pub.bind("tcp://127.0.0.1:5562")

    print("[*] Fetcher Worker ready. Listening for commands...")

    # ---- Cookie config (read at BOOT - restart fetcher after changing) ----
    s = load_settings()
    cookies_file = (s.get("yt_cookies_file") or "").strip()
    cookies_browser = (s.get("yt_cookies_from_browser") or "").strip().lower()

    cookie_opts = {}
    use_cookies = False
    if cookies_file and os.path.exists(cookies_file):
        cookie_opts["cookiefile"] = cookies_file
        use_cookies = True
        print(f"[*] yt-dlp: cookies file -> {cookies_file}")
    elif cookies_file:
        print(f"[!] yt_cookies_file is set but the file was not found: {cookies_file}")
    if not use_cookies and cookies_browser:
        cookie_opts["cookiesfrombrowser"] = (cookies_browser,)
        use_cookies = True
        print(f"[*] yt-dlp: cookies from browser -> {cookies_browser}")
    if not use_cookies:
        print("[!] yt-dlp: NO cookies configured - YouTube bot-check may block "
              "downloads. See README (yt cookies) section. To fix: set "
              "yt_cookies_from_browser or yt_cookies_file in settings.json.")

    # player_client workaround only helps when NOT using cookies; with cookies,
    # yt-dlp defaults work better.
    extractor_args = None if use_cookies else {'youtube': ['player_client=web_safari']}

    def base_opts(outtmpl):
        o = {
            'writethumbnail': True,
            'outtmpl': outtmpl,
            'noplaylist': False,
            'quiet': True,
            'no_warnings': True,
            'ignoreerrors': True,
        }
        if extractor_args:
            o['extractor_args'] = extractor_args
        o.update(cookie_opts)
        return o

    def notify_failed(query, reason):
        """Surface download failures in the UI chat instead of failing silently."""
        ui_pub.send_json({"type": "download_failed", "query": query, "reason": reason})

    while True:
        try:
            msg = fetch_socket.recv_json()
            action = msg.get("action")
            query = msg.get("query")
            media_type = msg.get("media_type", "video")

            if action == "download" and query:
                print(f"\n[*] Initiating {media_type.upper()} Download for: {query}")

                if media_type == "audio":
                    ydl_opts = {
                        'format': 'bestaudio/best',
                        'postprocessors': [{
                            'key': 'FFmpegExtractAudio',
                            'preferredcodec': 'm4a',
                            'preferredquality': '192',
                        }],
                        **base_opts('downloads/audio/%(title)s.%(ext)s'),
                    }
                else:
                    ydl_opts = {
                        'format': 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best',
                        **base_opts('downloads/video/%(title)s.%(ext)s'),
                    }

                search_query = query if query.startswith("http") else f"ytsearch1:{query}"

                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    info = ydl.extract_info(search_query, download=True)

                    # With ignoreerrors, a fully-blocked run returns None or an
                    # empty entry list instead of raising - catch both here.
                    entries = []
                    if info:
                        entries = [e for e in (info.get('entries') or [info]) if e is not None]

                    if not info or not entries:
                        print(f"[!] Download failed for '{query}' (no usable result from YouTube)")
                        notify_failed(query, (
                            "YouTube returned no result - usually the 'Sign in to confirm "
                            "you're not a bot' check. Fix: update yt-dlp, then set "
                            "yt_cookies_from_browser (e.g. \"firefox\", logged into YouTube) "
                            "or yt_cookies_file (cookies.txt) in settings.json and restart. "
                            "Details: logs/fetcher.log"))
                        continue

                    logged = 0
                    with sqlite3.connect("agentic_player.db") as conn:
                        cursor = conn.cursor()
                        for entry in entries:
                            title = entry.get('title', 'Unknown Title')
                            artist = entry.get('uploader', 'Unknown Artist')
                            duration = entry.get('duration')

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
                                    INSERT INTO tracks (title, artist, file_path, thumbnail_path, genre, duration)
                                    VALUES (?, ?, ?, ?, ?, ?)
                                    ON CONFLICT(file_path) DO UPDATE SET
                                        title=excluded.title,
                                        artist=excluded.artist,
                                        thumbnail_path=excluded.thumbnail_path,
                                        duration=excluded.duration
                                """, (title, artist, file_path, thumb_path, None, duration))
                                logged += 1
                                print(f"[*] Logged {media_type} to DB: {title}")
                        conn.commit()

                    if logged == 0:
                        print(f"[!] Download of '{query}' produced no files on disk")
                        notify_failed(query, (
                            "YouTube search matched but nothing landed on disk - "
                            "check logs/fetcher.log for the yt-dlp error."))
                    else:
                        sync_downloads()
                        ui_pub.send_json({"type": "download_complete"})

        except Exception as e:
            print(f"[!] Fetcher Error: {e}")


if __name__ == "__main__":
    start_fetcher_worker()
