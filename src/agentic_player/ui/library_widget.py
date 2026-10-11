from PySide6.QtWidgets import (QWidget, QVBoxLayout, QTreeWidget, QTreeWidgetItem, QLabel,
                                QLineEdit, QTabWidget, QMenu, QInputDialog, QMessageBox)
from PySide6.QtCore import Signal, Qt
from agentic_player.core.db_manager import DatabaseManager

ROLE_PATH = 256
ROLE_ID = 257
ROLE_GENRE = 258


def fmt_duration(seconds):
    try:
        seconds = int(float(seconds))
    except (TypeError, ValueError):
        return ""
    if seconds <= 0:
        return ""
    m, s = divmod(seconds, 60)
    return f"{m}:{s:02d}"


class LibraryWidget(QWidget):
    """Double-clicking a track plays its containing group (artist / genre /
    playlist), starting at that track. Group headers play the whole group."""
    play_collection_requested = Signal(list, str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.db = DatabaseManager()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)

        self.summary_label = QLabel("Library")
        self.summary_label.setObjectName("summaryLabel")
        layout.addWidget(self.summary_label)

        self.search_bar = QLineEdit()
        self.search_bar.setPlaceholderText("🔍 Search artists, songs, genres, playlists...")
        self.search_bar.setObjectName("searchBar")
        self.search_bar.textChanged.connect(self._filter_library)
        layout.addWidget(self.search_bar)

        self.tabs = QTabWidget()
        self.audio_tree = self._make_tree(["Artist / Title", "Tracks"])
        self.video_tree = self._make_tree(["Artist / Title", "Videos"])
        self.genre_tree = self._make_tree(["Genre", "Tracks"])
        self.playlist_tree = self._make_tree(["Playlist", "Tracks"])

        self.tabs.addTab(self.audio_tree, "🎵 Audio")
        self.tabs.addTab(self.video_tree, "🎬 Video")
        self.tabs.addTab(self.genre_tree, "🎸 Genres")
        self.tabs.addTab(self.playlist_tree, "📃 Playlists")
        layout.addWidget(self.tabs)

        self.refresh_library()

    # ---------- tree construction ----------

    def _make_tree(self, headers):
        tree = QTreeWidget()
        tree.setHeaderLabels(headers)
        tree.setColumnWidth(0, 180)
        tree.itemDoubleClicked.connect(self._on_track_activated)
        tree.setContextMenuPolicy(Qt.CustomContextMenu)
        tree.customContextMenuRequested.connect(lambda pos, t=tree: self._on_context_menu(t, pos))
        return tree

    def _track_item(self, parent, track, icon="🎵"):
        t_id, title, artist, file_path, _thumb, genre, duration = track
        label = title if title else "Untitled"
        text = f"{icon} {label} — {artist}" if artist else f"{icon} {label}"
        item = QTreeWidgetItem(parent, [text, fmt_duration(duration)])
        item.setData(0, ROLE_ID, t_id)
        item.setData(0, ROLE_PATH, file_path)
        item.setData(0, ROLE_GENRE, genre or "")
        item.setToolTip(0, file_path)
        return item

    def refresh_library(self):
        for tree in (self.audio_tree, self.video_tree, self.genre_tree, self.playlist_tree):
            tree.clear()

        all_tracks = self.db.get_all_tracks()
        playlists = self.db.get_playlists()

        n_audio = sum(1 for t in all_tracks if "downloads/audio" in (t[3] or "").replace("\\", "/"))
        n_video = sum(1 for t in all_tracks if "downloads/video" in (t[3] or "").replace("\\", "/"))
        self.summary_label.setText(
            f"🎵 {n_audio} | 🎬 {n_video} | 🎸 genres: {self._genre_count(all_tracks)} | 📃 {len(playlists)}"
        )

        # Audio / Video: grouped by artist
        by_artist = {}
        for t in all_tracks:
            by_artist.setdefault(t[2] or "Unknown Artist", []).append(t)
        for artist, tracks in by_artist.items():
            audio = [t for t in tracks if "downloads/audio" in (t[3] or "").replace("\\", "/")]
            video = [t for t in tracks if "downloads/video" in (t[3] or "").replace("\\", "/")]
            if audio:
                head = QTreeWidgetItem(self.audio_tree, [f"👤 {artist}", f"{len(audio)} tracks"])
                for t in audio:
                    self._track_item(head, t, "🎵")
            if video:
                head = QTreeWidgetItem(self.video_tree, [f"👤 {artist}", f"{len(video)} videos"])
                for t in video:
                    self._track_item(head, t, "🎬")

        # Genres
        by_genre = {}
        for t in all_tracks:
            g = (t[5] or "").strip() or "Unknown"
            by_genre.setdefault(g, []).append(t)
        for genre, tracks in sorted(by_genre.items(), key=lambda kv: (-len(kv[1]), kv[0])):
            head = QTreeWidgetItem(self.genre_tree, [f"🎸 {genre}", f"{len(tracks)} tracks"])
            for t in tracks:
                self._track_item(head, t, "🎵")

        # Playlists
        if not playlists:
            hint = QTreeWidgetItem(self.playlist_tree, ["➕ Right-click here to create a playlist", ""])
            hint.setFlags(hint.flags() & ~Qt.ItemIsEnabled)
        for pid, name, count in playlists:
            head = QTreeWidgetItem(self.playlist_tree, [f"📃 {name}", f"{count} tracks"])
            head.setData(0, ROLE_ID, None)  # group node marker (not a track)
            for t in self.db.get_playlist_tracks(pid):
                self._track_item(head, t, "🎵")

        if self.search_bar.text():
            self._filter_library(self.search_bar.text())

    def _genre_count(self, tracks):
        return len({(t[5] or "").strip() or "Unknown" for t in tracks})

    # ---------- playback ----------

    def _visible_child_paths(self, head):
        paths = []
        for i in range(head.childCount()):
            child = head.child(i)
            p = child.data(0, ROLE_PATH)
            if p and not child.isHidden():
                paths.append(p)
        return paths

    def _visible_child_ids(self, head):
        ids = []
        for i in range(head.childCount()):
            child = head.child(i)
            tid = child.data(0, ROLE_ID)
            if tid is not None and not child.isHidden():
                ids.append(tid)
        return ids

    def _on_track_activated(self, item, column):
        head = item.parent() or item
        files = self._visible_child_paths(head)
        path = item.data(0, ROLE_PATH)
        if path:
            start = path
            if start not in files:
                files.append(start)
        elif files:
            start = files[0]  # group header: play whole group
        else:
            return
        self.play_collection_requested.emit(files, start)

    # ---------- context menus ----------

    def _on_context_menu(self, tree, pos):
        item = tree.itemAt(pos)
        menu = QMenu(self)

        if item is None:
            if tree is self.playlist_tree:
                menu.addAction("✨ New playlist…", self._new_playlist_dialog)
            menu.exec(tree.viewport().mapToGlobal(pos))
            return

        track_id = item.data(0, ROLE_ID) if item.parent() else None
        head = item.parent() or item

        if track_id is not None:
            # A single track
            add_menu = menu.addMenu("➕ Add to playlist")
            self._populate_playlist_menu(add_menu, lambda pid: self._add_ids_to(pid, [track_id]))
            menu.addSeparator()
            menu.addAction("🎸 Set genre…", lambda: self._set_genre_for([item]))

        elif tree is self.playlist_tree and item.parent() is None and item.childCount() >= 0 and item.text(0).startswith("📃"):
            # A playlist header
            pid = None
            for cand_id, cand_name, _ in self.db.get_playlists():
                if f"📃 {cand_name}" == item.text(0):
                    pid = cand_id
                    break
            if pid is None:
                menu.exec(tree.viewport().mapToGlobal(pos))
                return
            menu.addAction("▶ Play all", lambda: self._play_playlist(pid))
            menu.addSeparator()
            menu.addAction("✏️ Rename…", lambda: self._rename_playlist(pid, item.text(0)[2:]))
            menu.addAction("🗑 Delete playlist", lambda: self._delete_playlist(pid, item.text(0)[2:]))
            menu.addSeparator()
            add_menu = menu.addMenu("➕ Add all to playlist")
            self._populate_playlist_menu(add_menu, lambda npid: self._add_ids_to(npid, self._visible_child_ids(item)))

        else:
            # Artist / genre header
            ids = self._visible_child_ids(item)
            if ids:
                add_menu = menu.addMenu(f"➕ Add all {len(ids)} tracks to playlist")
                self._populate_playlist_menu(add_menu, lambda pid: self._add_ids_to(pid, ids))

        menu.exec(tree.viewport().mapToGlobal(pos))

    def _populate_playlist_menu(self, menu, add_callback):
        for pid, name, count in self.db.get_playlists():
            act = menu.addAction(f"{name} ({count})")
            act.triggered.connect(lambda checked=False, pid=pid: add_callback(pid))
        menu.addSeparator()
        menu.addAction("✨ New playlist…", lambda: self._new_playlist_then_add(add_callback))

    # ---------- playlist / genre mutations ----------

    def _new_playlist_dialog(self):
        name, ok = QInputDialog.getText(self, "New playlist", "Playlist name:")
        if ok and name.strip():
            pid = self.db.create_playlist(name)
            if pid is None:
                QMessageBox.warning(self, "New playlist", f"A playlist named '{name}' already exists.")
            self.refresh_library()

    def _new_playlist_then_add(self, add_callback):
        name, ok = QInputDialog.getText(self, "New playlist", "Playlist name:")
        if not (ok and name.strip()):
            return
        pid = self.db.create_playlist(name)
        if pid is None:
            QMessageBox.warning(self, "New playlist", f"A playlist named '{name}' already exists.")
            return
        add_callback(pid)
        self.refresh_library()

    def _add_ids_to(self, pid, ids):
        for tid in ids:
            self.db.add_track_to_playlist(pid, tid)
        self.refresh_library()

    def _rename_playlist(self, pid, old_name):
        name, ok = QInputDialog.getText(self, "Rename playlist", "New name:", text=old_name)
        if not (ok and name.strip()):
            return
        if not self.db.rename_playlist(pid, name):
            QMessageBox.warning(self, "Rename playlist", f"A playlist named '{name}' already exists.")
        self.refresh_library()

    def _delete_playlist(self, pid, name):
        if QMessageBox.question(self, "Delete playlist", f"Delete '{name}'? (Files are kept.)") == QMessageBox.Yes:
            self.db.delete_playlist(pid)
            self.refresh_library()

    def _play_playlist(self, pid):
        tracks = self.db.get_playlist_tracks(pid)
        files = [t[3] for t in tracks if t[3]]
        if files:
            self.play_collection_requested.emit(files, files[0])

    def _set_genre_for(self, items):
        for item in items:
            tid = item.data(0, ROLE_ID)
            if tid is None:
                continue
            current = item.data(0, ROLE_GENRE) or ""
            text, ok = QInputDialog.getText(self, "Set genre", f"Genre for '{item.text(0)}':", text=current)
            if not ok:
                return
            self.db.set_track_genre(tid, text.strip())
        self.refresh_library()

    # ---------- search ----------

    def _filter_library(self, text):
        text = text.lower()
        for tree in [self.audio_tree, self.video_tree, self.genre_tree, self.playlist_tree]:
            for i in range(tree.topLevelItemCount()):
                head = tree.topLevelItem(i)
                head_match = text in head.text(0).lower()

                match_count = 0
                for j in range(head.childCount()):
                    child = head.child(j)
                    if text in child.text(0).lower() or head_match:
                        child.setHidden(False)
                        match_count += 1
                    else:
                        child.setHidden(True)

                if head_match or match_count > 0:
                    head.setHidden(False)
                    if text:
                        head.setExpanded(True)
                else:
                    head.setHidden(True)
