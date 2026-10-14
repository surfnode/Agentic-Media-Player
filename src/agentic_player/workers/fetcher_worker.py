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

    # ---- Download config (read at BOOT - restart after changing) -------
    s = load_settings()

    cookie_opts = {}
    cookie_note = "none"
    cookies_file = (s.get("yt_cookies_file") or "").strip()
    cookies_browser = (s.get("yt_cookies_from_browser") or "").strip().lower()
    if cookies_file and os.path.exists(cookies_file):
        cookie_opts["cookiefile"] = cookies_file
        cookie_note = f"file:{cookies_file}"
    elif cookies_file:
        print(f"[!] yt_cookies_file set but not found: {cookies_file}")
    if not cookie_opts and cookies_browser:
        cookie_opts["cookiesfrombrowser"] = (cookies_browser,)
        cookie_note = f"browser:{cookies_browser}"
    if not cookie_opts:
        print("[!] yt-dlp: NO cookies - YouTube bot-check may still block some "
              "downloads. Strongest fix: yt_cookies_from_browser in settings.json "
              "(see README). The client ladder will try to cope without them.")

    CLIENT_LADDER = [c.strip() for c in (s.get("yt_player_clients") or "").split(",")
                      if c.strip()] or ["tv", "web_safari", "mweb"]
    print(f"[*] yt-dlp: client ladder {CLIENT_LADDER} | cookies: {cookie_note} | "
          f"yt-dlp {yt_dlp.version.__version__}")

    import shutil
    deno_path = shutil.which("deno")
    if deno_path:
        print(f"[*] JS runtime (deno): {deno_path}")
    else:
        print("[!] DENO NOT FOUND in PATH - YouTube downloads WILL FAIL "
              "(EJS challenge unsolvable). Fix: run.sh must export $HOME/.deno/bin")

    def notify_failed(query, reason):
        ui_pub.send_json({"type": "download_failed", "query": query, "reason": reason})

    def run_download(query, media_type, count):
        """Try each player client in order until YouTube lets us through.
        Returns (entries, last_error, winning_client)."""
        if query.startswith("http"):
            search = query                      # real URL: playlist links work as-is
        elif count and count > 1:
            search = f"ytsearch{count}:{query}"  # top-N search grab
        else:
            search = f"ytsearch1:{query}"

        last_err = "no attempts made"
        for client in CLIENT_LADDER:
            opts = {
                'writethumbnail': True,
                'noplaylist': False,
                'quiet': True,
                'no_warnings': True,
                'ignoreerrors': True,
                'extractor_args': {'youtube': [f'player_client={client}']},
            }
            opts.update(cookie_opts)
            if media_type == "audio":
                opts['format'] = 'bestaudio/best'
                opts['postprocessors'] = [{
                    'key': 'FFmpegExtractAudio',
                    'preferredcodec': 'm4a',
                    'preferredquality': '192',
                }]
                opts['outtmpl'] = 'downloads/audio/%(title)s.%(ext)s'
            else:
                opts['format'] = 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best'
                opts['outtmpl'] = 'downloads/video/%(title)s.%(ext)s'

            print(f"[*] yt-dlp attempt: client={client} | cookies={cookie_note} | search={search!r}")
            try:
                with yt_dlp.YoutubeDL(opts) as ydl:
                    info = ydl.extract_info(search, download=True)
            except Exception as e:
                last_err = str(e)
                print(f"[!] client={client} raised: {last_err[:180]}")
                continue

            entries = []
            if info:
                raw = info.get('entries') or [info]
                entries = [e for e in raw if e is not None]
            if entries:
                return entries, None, client
            last_err = "YouTube returned no usable result (bot-check or no match)"
            print(f"[!] client={client}: no entries")

        return [], last_err, None

    while True:
        try:
            msg = fetch_socket.recv_json()
            action = msg.get("action")
            query = (msg.get("query") or "").strip()
            media_type = msg.get("media_type", "video")
            raw_count = msg.get("count")
            count = max(1, min(50, int(raw_count))) if raw_count else 1

            if action == "download" and query:
                print(f"\n[*] Initiating {media_type.upper()} download: {query!r} (count={count})")

                entries, last_err, winner = run_download(query, media_type, count)

                if not entries:
                    reason = (f"{last_err} [clients tried: {', '.join(CLIENT_LADDER)}; "
                              f"cookies: {cookie_note}] First: update yt-dlp "
                              f"(venv/bin/pip install -U yt-dlp). If it persists, set "
                              f"yt_cookies_from_browser in settings.json. Details: logs/fetcher.log")
                    print(f"[!] Download failed for '{query}': {last_err}")
                    notify_failed(query, reason)
                    continue

                print(f"[*] Client '{winner}' got through - {len(entries)} entries")
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
                    notify_failed(query, "Search matched but nothing landed on disk - check logs/fetcher.log")
                else:
                    sync_downloads()
                    ui_pub.send_json({"type": "download_complete"})

        except Exception as e:
            print(f"[!] Fetcher Error: {e}")


if __name__ == "__main__":
    start_fetcher_worker()
