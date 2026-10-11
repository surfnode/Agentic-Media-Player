import os
import sqlite3


class DatabaseManager:
    def __init__(self, db_path="agentic_player.db"):
        self.db_path = db_path
        self._init_db()
        self._migrate()
        self._backfill_metadata()

    def _connect(self):
        conn = sqlite3.connect(self.db_path)
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    def _init_db(self):
        with self._connect() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS tracks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    title TEXT,
                    artist TEXT,
                    album TEXT,
                    file_path TEXT UNIQUE,
                    thumbnail_path TEXT
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS playlists (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT UNIQUE NOT NULL,
                    created_at TEXT DEFAULT (datetime('now','localtime'))
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS playlist_tracks (
                    playlist_id INTEGER NOT NULL REFERENCES playlists(id) ON DELETE CASCADE,
                    track_id INTEGER NOT NULL REFERENCES tracks(id) ON DELETE CASCADE,
                    position INTEGER NOT NULL DEFAULT 0,
                    added_at TEXT DEFAULT (datetime('now','localtime')),
                    PRIMARY KEY (playlist_id, track_id)
                )
            """)
            conn.commit()

    def _migrate(self):
        """Idempotent column adds for DBs created before M4a."""
        with self._connect() as conn:
            cols = [r[1] for r in conn.execute("PRAGMA table_info(tracks)").fetchall()]
            if "genre" not in cols:
                conn.execute("ALTER TABLE tracks ADD COLUMN genre TEXT")
            if "duration" not in cols:
                conn.execute("ALTER TABLE tracks ADD COLUMN duration REAL")
            conn.commit()

    def _backfill_metadata(self):
        """One-time-ish: fill duration/genre for existing tracks via TinyTag.
        Only touches rows where duration is still NULL. Manual genres are
        never overwritten (genre is only set when currently empty)."""
        try:
            from tinytag import TinyTag
        except ImportError:
            return

        with self._connect() as conn:
            rows = conn.execute(
                "SELECT id, file_path FROM tracks WHERE duration IS NULL"
            ).fetchall()

        filled = 0
        for track_id, file_path in rows:
            if not file_path or not os.path.exists(file_path):
                continue
            try:
                tag = TinyTag.get(file_path)
                duration = int(tag.duration) if tag.duration else None
                genre = (tag.genre or "").strip() or None
            except Exception:
                continue
            with self._connect() as conn:
                conn.execute(
                    """UPDATE tracks SET
                         duration = COALESCE(?, duration),
                         genre = CASE WHEN TRIM(COALESCE(genre,'')) = ''
                                      THEN ? ELSE genre END
                       WHERE id = ?""",
                    (duration, genre, track_id),
                )
            filled += 1
        if filled:
            print(f"[db] Backfilled duration/genre for {filled} tracks.")

    # ---------- tracks ----------

    def get_tracks_per_artist(self):
        with self._connect() as conn:
            return conn.execute("""
                SELECT COALESCE(artist, 'Unknown Artist') AS artist_name, COUNT(*)
                FROM tracks GROUP BY artist_name
                ORDER BY COUNT(*) DESC, artist_name ASC
            """).fetchall()

    def get_all_tracks(self):
        with self._connect() as conn:
            return conn.execute("""
                SELECT id, title, artist, file_path, thumbnail_path,
                       COALESCE(genre, ''), COALESCE(duration, 0)
                FROM tracks ORDER BY id DESC
            """).fetchall()

    def set_track_genre(self, track_id, genre):
        with self._connect() as conn:
            conn.execute("UPDATE tracks SET genre = ? WHERE id = ?", (genre.strip(), track_id))
            conn.commit()

    # ---------- playlists ----------

    def get_playlists(self):
        with self._connect() as conn:
            return conn.execute("""
                SELECT p.id, p.name,
                       (SELECT COUNT(*) FROM playlist_tracks pt WHERE pt.playlist_id = p.id)
                FROM playlists p ORDER BY p.name COLLATE NOCASE
            """).fetchall()

    def create_playlist(self, name):
        """Returns new playlist id, or None if the name already exists."""
        try:
            with self._connect() as conn:
                cur = conn.execute("INSERT INTO playlists (name) VALUES (?)", (name.strip(),))
                conn.commit()
                return cur.lastrowid
        except sqlite3.IntegrityError:
            return None

    def rename_playlist(self, playlist_id, name):
        try:
            with self._connect() as conn:
                conn.execute("UPDATE playlists SET name = ? WHERE id = ?", (name.strip(), playlist_id))
                conn.commit()
            return True
        except sqlite3.IntegrityError:
            return False

    def delete_playlist(self, playlist_id):
        with self._connect() as conn:
            conn.execute("DELETE FROM playlists WHERE id = ?", (playlist_id,))
            conn.commit()

    def add_track_to_playlist(self, playlist_id, track_id):
        with self._connect() as conn:
            conn.execute("""
                INSERT OR IGNORE INTO playlist_tracks (playlist_id, track_id, position)
                SELECT ?, ?, COALESCE(MAX(position) + 1, 0)
                FROM playlist_tracks WHERE playlist_id = ?
            """, (playlist_id, track_id, playlist_id))
            conn.commit()

    def remove_track_from_playlist(self, playlist_id, track_id):
        with self._connect() as conn:
            conn.execute(
                "DELETE FROM playlist_tracks WHERE playlist_id = ? AND track_id = ?",
                (playlist_id, track_id),
            )
            conn.commit()

    def get_playlist_tracks(self, playlist_id):
        with self._connect() as conn:
            return conn.execute("""
                SELECT t.id, t.title, t.artist, t.file_path, t.thumbnail_path,
                       COALESCE(t.genre, ''), COALESCE(t.duration, 0)
                FROM playlist_tracks pt JOIN tracks t ON t.id = pt.track_id
                WHERE pt.playlist_id = ?
                ORDER BY pt.position, pt.added_at, t.id
            """, (playlist_id,)).fetchall()
