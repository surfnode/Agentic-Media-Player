import sqlite3

class DatabaseManager:
    def __init__(self, db_path="agentic_player.db"):
        self.db_path = db_path
        self._init_db()

    def _init_db(self):
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS tracks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    title TEXT,
                    artist TEXT,
                    album TEXT,
                    file_path TEXT UNIQUE,
                    thumbnail_path TEXT
                )
            """)
            conn.commit()

    def get_tracks_per_artist(self):
        """Returns a list of tuples: (artist, track_count)"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT COALESCE(artist, 'Unknown Artist') AS artist_name, COUNT(*) AS count
                FROM tracks
                GROUP BY artist_name
                ORDER BY count DESC, artist_name ASC
            """)
            return cursor.fetchall()

    def get_all_tracks(self):
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT id, title, artist, file_path FROM tracks ORDER BY id DESC")
            return cursor.fetchall()
