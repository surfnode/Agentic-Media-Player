"""Page widgets for the YT-style shell: card grids, library trees,
playlist management, and the Now Playing stage."""
import os
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QScrollArea,
                                QLabel, QListWidget, QTabWidget, QTreeWidget, QTreeWidgetItem,
                                QMenu, QInputDialog, QMessageBox, QPushButton, QStackedWidget,
                                QListWidgetItem)
from PySide6.QtCore import Signal, Qt
from PySide6.QtGui import QPixmap
from agentic_player.core.db_manager import DatabaseManager

ROLE_PATH = 256
ROLE_ID = 257


def fmt_duration(seconds):
    try:
        seconds = int(float(seconds))
    except (TypeError, ValueError):
        return ""
    if seconds <= 0:
        return ""
    m, s = divmod(seconds, 60)
    h, m = divmod(m, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def load_thumb(path, w, h):
    if path and os.path.exists(path):
        pm = QPixmap(path)
        if not pm.isNull():
            return pm.scaled(w, h, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)
    return QPixmap()


# ---------------------------------------------------------------- cards

class TrackCard(QWidget):
    """A YouTube-style card: 16:9 thumbnail, title, artist/duration."""
    activated = Signal(object)
    menu_requested = Signal(object, object)    # card, global pos

    def __init__(self, track, parent=None):
        super().__init__(parent)
        self.t_id, self.title, self.artist, self.file_path, self.thumb, self.genre, self.duration = track
        self.setFixedWidth(200)
        self.setCursor(Qt.PointingHandCursor)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(4)

        self.thumb_label = QLabel()
        self.thumb_label.setFixedSize(184, 104)
        self.thumb_label.setObjectName("cardThumb")
        self.thumb_label.setAlignment(Qt.AlignCenter)
        pm = load_thumb(self.thumb, 184, 104)
        if pm.isNull():
            self.thumb_label.setText("🎵" if "downloads/audio" in (self.file_path or "") else "🎬")
        else:
            self.thumb_label.setPixmap(pm)
        layout.addWidget(self.thumb_label)

        t = QLabel(self.title or "Untitled")
        t.setObjectName("cardTitle")
        t.setWordWrap(True)
        t.setMaximumHeight(36)
        layout.addWidget(t)

        sub = QLabel(f"{self.artist or 'Unknown Artist'} · {fmt_duration(self.duration)}")
        sub.setObjectName("cardSub")
        sub.setWordWrap(True)
        layout.addWidget(sub)

    def mouseReleaseEvent(self, e):
        if e.button() == Qt.LeftButton:
            self.activated.emit(self)

    def contextMenuEvent(self, e):
        self.menu_requested.emit(self, e.globalPos())


class CardSection(QWidget):
    """Header + centered wrapped grid of cards inside a scroll area.
    The grid stretches so cards never bleed off the right edge - the
    scroll area handles overflow vertically."""
    play_requested = Signal(list, str)

    def __init__(self, title, subtitle="", parent=None):
        super().__init__(parent)
        self.cards = []
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 12)

        head = QHBoxLayout()
        self.header_label = QLabel(title)
        self.header_label.setObjectName("sectionHeader")
        head.addWidget(self.header_label)
        if subtitle:
            s = QLabel(subtitle)
            s.setObjectName("cardSub")
            head.addWidget(s)
        head.addStretch()
        layout.addLayout(head)

        self.grid_host = QWidget()
        self.grid = QGridLayout(self.grid_host)
        self.grid.setContentsMargins(0, 4, 0, 0)
        self.grid.setSpacing(8)
        self.grid.setAlignment(Qt.AlignTop | Qt.AlignHCenter)
        layout.addWidget(self.grid_host)

    def add_card(self, card):
        card.activated.connect(self._card_clicked)
        self.cards.append(card)
        i = len(self.cards) - 1
        self.grid.addWidget(card, i // 4, i % 4)

    def _card_clicked(self, card):
        files = [c.file_path for c in self.cards if c.file_path]
        if card.file_path and card.file_path in files:
            self.play_requested.emit(files, card.file_path)

    def set_filter(self, text):
        text = text.lower()
        visible = 0
        for c in self.cards:
            hit = (text in (c.title or "").lower()
                   or text in (c.artist or "").lower()
                   or text in (c.genre or "").lower())
            c.setVisible(hit)
            visible += hit
        self.grid_host.setVisible(visible > 0)
        self.header_label.setVisible(visible > 0)
        return visible

    def clear_cards(self):
        for c in self.cards:
            c.setParent(None)
            c.deleteLater()
        self.cards = []


class PlaylistSection(CardSection):
    """CardSection that knows its playlist id (for header menus)."""
    def __init__(self, pid, title, subtitle="", parent=None):
        super().__init__(title, subtitle, parent)
        self.pid = pid
        self.header_label.setContextMenuPolicy(Qt.CustomContextMenu)


# ---------------------------------------------------------------- pages

class HomePage(QWidget):
    """YT feed: recently added tracks as a card grid."""
    play_requested = Signal(list, str)

    def __init__(self, db, parent=None):
        super().__init__(parent)
        self.db = db
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.NoFrame)
        outer.addWidget(scroll)
        self.body = QWidget()
        self.vbox = QVBoxLayout(self.body)
        self.vbox.setContentsMargins(16, 16, 16, 16)
        self.vbox.addStretch()
        scroll.setWidget(self.body)
        self.section = None
        self.refresh()

    def refresh(self):
        if self.section:
            self.section.setParent(None)
            self.section.deleteLater()
        tracks = self.db.get_all_tracks()
        self.section = CardSection("Recently added", f"{len(tracks)} tracks")
        self.section.play_requested.connect(self.play_requested)
        for t in tracks:
            self.section.add_card(TrackCard(t))
        self.vbox.insertWidget(0, self.section)

    def set_filter(self, text):
        self.section.set_filter(text)


class GenresPage(QWidget):
    play_requested = Signal(list, str)
    menu_requested = Signal(object, object)    # card, global pos

    def __init__(self, db, parent=None):
        super().__init__(parent)
        self.db = db
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.NoFrame)
        outer.addWidget(scroll)
        self.body = QWidget()
        self.vbox = QVBoxLayout(self.body)
        self.vbox.setContentsMargins(16, 16, 16, 16)
        self.vbox.addStretch()
        scroll.setWidget(self.body)
        self.sections = []
        self.refresh()

    def refresh(self):
        for s in self.sections:
            s.setParent(None)
            s.deleteLater()
        self.sections = []
        by_genre = {}
        for t in self.db.get_all_tracks():
            g = (t[5] or "").strip() or "Unknown"
            by_genre.setdefault(g, []).append(t)
        for genre, tracks in sorted(by_genre.items(), key=lambda kv: (-len(kv[1]), kv[0])):
            s = CardSection(f"🎸 {genre}", f"{len(tracks)} tracks")
            s.play_requested.connect(self.play_requested)
            for t in tracks:
                card = TrackCard(t)
                card.menu_requested.connect(self.menu_requested.emit)
                s.add_card(card)
            self.sections.append(s)
            self.vbox.insertWidget(self.vbox.count() - 1, s)

    def set_filter(self, text):
        for s in self.sections:
            s.set_filter(text)


class PlaylistsPage(QWidget):
    play_requested = Signal(list, str)
    # 3 values: (card, owning section, global pos).
    menu_requested = Signal(object, object, object)

    def __init__(self, db, parent=None):
        super().__init__(parent)
        self.db = db
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.NoFrame)
        outer.addWidget(scroll)
        self.body = QWidget()
        self.vbox = QVBoxLayout(self.body)
        self.vbox.setContentsMargins(16, 16, 16, 16)

        top = QHBoxLayout()
        new_btn = QPushButton("✨ New playlist")
        new_btn.clicked.connect(self._new_playlist)
        top.addWidget(new_btn)
        top.addStretch()
        self.vbox.addLayout(top)
        self.vbox.addStretch()
        scroll.setWidget(self.body)
        self.sections = []
        self.refresh()

    def refresh(self):
        for s in self.sections:
            s.setParent(None)
            s.deleteLater()
        self.sections = []
        playlists = self.db.get_playlists()
        if not playlists:
            hint = QLabel("No playlists yet — create one, then right-click any track to add it.")
            hint.setObjectName("cardSub")
            self.vbox.insertWidget(1, hint)
        for pid, name, count in playlists:
            s = PlaylistSection(pid, f"📃 {name}", f"{count} tracks")
            s.play_requested.connect(self.play_requested)
            s.header_label.customContextMenuRequested.connect(
                lambda pos, s=s: self._playlist_header_menu(s, pos))
            for t in self.db.get_playlist_tracks(pid):
                card = TrackCard(t)
                card.menu_requested.connect(
                    lambda c, p, s=s: self.menu_requested.emit(c, s, p))
                s.add_card(card)
            self.sections.append(s)
            self.vbox.insertWidget(self.vbox.count() - 1, s)

    def _new_playlist(self):
        name, ok = QInputDialog.getText(self, "New playlist", "Playlist name:")
        if ok and name.strip():
            if self.db.create_playlist(name) is None:
                QMessageBox.warning(self, "New playlist", f"'{name}' already exists.")
            self.refresh()

    def _playlist_header_menu(self, section, pos):
        pid, name = section.pid, section.header_label.text()[2:]
        files = [t[3] for t in self.db.get_playlist_tracks(pid) if t[3]]
        m = QMenu(self)
        if files:
            m.addAction("▶ Play all", lambda: self.play_requested.emit(files, files[0]))
        m.addSeparator()
        m.addAction("✏️ Rename…", lambda: self._rename(section))
        m.addAction("🗑 Delete", lambda: self._delete(section))
        m.exec(section.header_label.mapToGlobal(pos))

    def _rename(self, section):
        old = section.header_label.text()[2:]
        name, ok = QInputDialog.getText(self, "Rename playlist", "New name:", text=old)
        if ok and name.strip():
            if not self.db.rename_playlist(section.pid, name):
                QMessageBox.warning(self, "Rename playlist", f"'{name}' already exists.")
            self.refresh()

    def _delete(self, section):
        name = section.header_label.text()[2:]
        if QMessageBox.question(self, "Delete playlist", f"Delete '{name}'? (Files are kept.)") == QMessageBox.Yes:
            self.db.delete_playlist(section.pid)
            self.refresh()

    def set_filter(self, text):
        for s in self.sections:
            s.set_filter(text)


class LibraryPage(QWidget):
    """Dense navigation trees (Audio/Video), grouped by artist."""
    play_requested = Signal(list, str)

    def __init__(self, db, parent=None):
        super().__init__(parent)
        self.db = db
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        self.tabs = QTabWidget()
        self.audio_tree = self._make_tree(["Artist / Title", "Tracks"])
        self.video_tree = self._make_tree(["Artist / Title", "Videos"])
        self.tabs.addTab(self.audio_tree, "🎵 Audio")
        self.tabs.addTab(self.video_tree, "🎬 Video")
        layout.addWidget(self.tabs)
        self.refresh()

    def _make_tree(self, headers):
        tree = QTreeWidget()
        tree.setHeaderLabels(headers)
        tree.setColumnWidth(0, 220)
        tree.itemDoubleClicked.connect(self._activated)
        return tree

    def refresh(self):
        self.audio_tree.clear()
        self.video_tree.clear()
        by_artist = {}
        for t in self.db.get_all_tracks():
            by_artist.setdefault(t[2] or "Unknown Artist", []).append(t)
        for artist, tracks in by_artist.items():
            audio = [t for t in tracks if "downloads/audio" in (t[3] or "").replace("\\", "/")]
            video = [t for t in tracks if "downloads/video" in (t[3] or "").replace("\\", "/")]
            if audio:
                head = QTreeWidgetItem(self.audio_tree, [f"👤 {artist}", f"{len(audio)} tracks"])
                for t in audio:
                    item = QTreeWidgetItem(head, [f"🎵 {t[1] or 'Untitled'}", fmt_duration(t[6])])
                    item.setData(0, ROLE_PATH, t[3])
            if video:
                head = QTreeWidgetItem(self.video_tree, [f"👤 {artist}", f"{len(video)} videos"])
                for t in video:
                    item = QTreeWidgetItem(head, [f"🎬 {t[1] or 'Untitled'}", fmt_duration(t[6])])
                    item.setData(0, ROLE_PATH, t[3])

    def _activated(self, item, column):
        head = item.parent() or item
        files = []
        for i in range(head.childCount()):
            p = head.child(i).data(0, ROLE_PATH)
            if p:
                files.append(p)
        path = item.data(0, ROLE_PATH)
        if not files:
            return
        start = path if path in files else files[0]
        self.play_requested.emit(files, start)

    def set_filter(self, text):
        text = text.lower()
        for tree in (self.audio_tree, self.video_tree):
            for i in range(tree.topLevelItemCount()):
                head = tree.topLevelItem(i)
                head_match = text in head.text(0).lower()
                n = 0
                for j in range(head.childCount()):
                    child = head.child(j)
                    hit = text in child.text(0).lower() or head_match
                    child.setHidden(not hit)
                    n += hit
                head.setHidden(not (head_match or n))
                if text and (head_match or n):
                    head.setExpanded(True)


class ArtVideoStage(QWidget):
    """Album art (index 0) / black video surface (index 1). VLC embeds into the surface."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.stack = QStackedWidget(self)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(self.stack)

        self.art_label = QLabel("🎵")
        self.art_label.setObjectName("stageArt")
        self.art_label.setAlignment(Qt.AlignCenter)
        self.stack.addWidget(self.art_label)

        self.video_surface = QWidget()
        self.video_surface.setObjectName("stageVideo")
        self.video_surface.setAttribute(Qt.WA_NativeWindow)
        self.video_surface.setMinimumSize(320, 180)
        self.stack.addWidget(self.video_surface)
        self.stack.setCurrentIndex(0)

    def show_media(self, is_video):
        self.stack.setCurrentIndex(1 if is_video else 0)


class NowPlayingPage(QWidget):
    """Big stage: video surface (VLC embeds here), album art, and Up Next."""
    upnext_play_requested = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(16, 16, 16, 16)
        outer.setSpacing(12)

        # Stage (video / album art)
        self.stage = ArtVideoStage()
        self.stage.setMinimumHeight(320)
        outer.addWidget(self.stage, 4)

        # Title / artist
        self.title_label = QLabel("Nothing playing")
        self.title_label.setObjectName("nowTitle")
        self.title_label.setWordWrap(True)
        self.artist_label = QLabel("")
        self.artist_label.setObjectName("cardSub")
        self.artist_label.setWordWrap(True)
        outer.addWidget(self.title_label)
        outer.addWidget(self.artist_label)

        # Up Next - horizontal scrolling row under the video (like YT).
        # No vertical split competing with the agent dock; always readable.
        up_header = QLabel("Up Next")
        up_header.setObjectName("sectionHeader")
        outer.addWidget(up_header)
        self.up_next = QListWidget()
        self.up_next.setObjectName("upNext")
        self.up_next.setFlow(QListWidget.LeftToRight)
        self.up_next.setWrapping(False)
        self.up_next.setFixedHeight(64)
        self.up_next.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.up_next.setWordWrap(True)
        self.up_next.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.up_next.currentRowChanged.connect(self._upnext_clicked_row)
        self._upnext_files = []
        outer.addWidget(self.up_next)

    @property
    def video_surface(self):
        return self.stage.video_surface

    def set_track(self, title, artist, thumb, is_video, file_path):
        self.title_label.setText(title or os.path.basename(file_path))
        self.artist_label.setText(artist or "")
        self.stage.show_media(is_video)
        if not is_video:
            pm = load_thumb(thumb, 480, 270)
            if not pm.isNull():
                self.stage.art_label.setPixmap(pm)
            else:
                self.stage.art_label.clear()

    def set_queue(self, files, start=None):
        """Fill Up Next from the play context. start=None = live update from
        the player (highlight current, list the rest after it)."""
        self.up_next.clear()
        self._upnext_files = [f for f in (files or []) if f]
        if not self._upnext_files:
            return
        if start and start in self._upnext_files:
            ordered = self._upnext_files[self._upnext_files.index(start):]
        else:
            ordered = self._upnext_files
        for f in ordered:
            item = QListWidgetItem(os.path.basename(f))
            self.up_next.addItem(item)

    def _upnext_clicked_row(self, row):
        """Click a row -> play that file (guard against signal storms)."""
        if row < 0 or row >= len(self._upnext_files):
            return
        target = self._upnext_files[row]
        self.up_next.blockSignals(True)
        self.up_next.setCurrentRow(-1)
        self.up_next.blockSignals(False)
        # emit play for a single file - main.py wires this to the player
        if hasattr(self, "upnext_play_requested"):
            self.upnext_play_requested.emit(target)
