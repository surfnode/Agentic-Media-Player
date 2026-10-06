from PySide6.QtWidgets import QWidget, QVBoxLayout, QTreeWidget, QTreeWidgetItem, QLabel, QLineEdit, QTabWidget
from PySide6.QtCore import Signal
from agentic_player.core.db_manager import DatabaseManager

class LibraryWidget(QWidget):
    play_requested = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.db = DatabaseManager()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)

        self.summary_label = QLabel("Library: 0 items")
        self.summary_label.setObjectName("summaryLabel")
        layout.addWidget(self.summary_label)
        
        self.search_bar = QLineEdit()
        self.search_bar.setPlaceholderText("🔍 Search artists or songs...")
        self.search_bar.setObjectName("searchBar")
        self.search_bar.textChanged.connect(self._filter_library)
        layout.addWidget(self.search_bar)

        self.tabs = QTabWidget()
        
        # Audio Tree
        self.audio_tree = QTreeWidget()
        self.audio_tree.setHeaderLabels(["Artist / Title", "Tracks"])
        self.audio_tree.setColumnWidth(0, 180)
        self.audio_tree.itemDoubleClicked.connect(self._on_item_double_clicked)
        
        # Video Tree
        self.video_tree = QTreeWidget()
        self.video_tree.setHeaderLabels(["Artist / Title", "Videos"])
        self.video_tree.setColumnWidth(0, 180)
        self.video_tree.itemDoubleClicked.connect(self._on_item_double_clicked)

        self.tabs.addTab(self.audio_tree, "🎵 Audio")
        self.tabs.addTab(self.video_tree, "🎬 Video")
        layout.addWidget(self.tabs)

        self.refresh_library()

    def refresh_library(self):
        self.audio_tree.clear()
        self.video_tree.clear()
        
        artist_counts = self.db.get_tracks_per_artist()
        all_tracks = self.db.get_all_tracks()

        # Safely replace backslashes for cross-platform path matching
        total_songs = len([t for t in all_tracks if "downloads/audio" in (t[3] or "").replace('\\', '/')])
        total_videos = len([t for t in all_tracks if "downloads/video" in (t[3] or "").replace('\\', '/')])
        
        self.summary_label.setText(f"🎵 Audio: {total_songs} | 🎬 Video: {total_videos}")

        for artist, _ in artist_counts:
            artist_tracks = [t for t in all_tracks if (t[2] or 'Unknown Artist') == artist]
            
            audio_tracks = [t for t in artist_tracks if "downloads/audio" in (t[3] or "").replace('\\', '/')]
            video_tracks = [t for t in artist_tracks if "downloads/video" in (t[3] or "").replace('\\', '/')]

            if audio_tracks:
                artist_item = QTreeWidgetItem(self.audio_tree, [f"👤 {artist}", f"{len(audio_tracks)} tracks"])
                for t_id, title, _, file_path in audio_tracks:
                    track_title = title if title else "Untitled Track"
                    track_item = QTreeWidgetItem(artist_item, [f"🎵 {track_title}", ""])
                    track_item.setData(0, 256, file_path)

            if video_tracks:
                artist_item = QTreeWidgetItem(self.video_tree, [f"👤 {artist}", f"{len(video_tracks)} videos"])
                for t_id, title, _, file_path in video_tracks:
                    track_title = title if title else "Untitled Video"
                    track_item = QTreeWidgetItem(artist_item, [f"🎬 {track_title}", ""])
                    track_item.setData(0, 256, file_path)
                
        if self.search_bar.text():
            self._filter_library(self.search_bar.text())

    def _filter_library(self, text):
        text = text.lower()
        for tree in [self.audio_tree, self.video_tree]:
            for i in range(tree.topLevelItemCount()):
                artist_item = tree.topLevelItem(i)
                artist_match = text in artist_item.text(0).lower()
                
                track_match_count = 0
                for j in range(artist_item.childCount()):
                    track_item = artist_item.child(j)
                    if text in track_item.text(0).lower() or artist_match:
                        track_item.setHidden(False)
                        track_match_count += 1
                    else:
                        track_item.setHidden(True)
                
                if artist_match or track_match_count > 0:
                    artist_item.setHidden(False)
                    if text:
                        artist_item.setExpanded(True)
                else:
                    artist_item.setHidden(True)

    def _on_item_double_clicked(self, item, column):
        file_path = item.data(0, 256)
        if file_path:
            self.play_requested.emit(file_path)
