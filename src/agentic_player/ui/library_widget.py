from PySide6.QtWidgets import QWidget, QVBoxLayout, QTreeWidget, QTreeWidgetItem, QLabel, QLineEdit
from PySide6.QtCore import Signal
from agentic_player.core.db_manager import DatabaseManager

class LibraryWidget(QWidget):
    play_requested = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.db = DatabaseManager()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)

        self.summary_label = QLabel("Library: 0 artists")
        self.summary_label.setStyleSheet("color: #a6adc8; font-size: 11px; margin-bottom: 4px;")
        layout.addWidget(self.summary_label)
        
        # --- NEW SEARCH BAR ---
        self.search_bar = QLineEdit()
        self.search_bar.setPlaceholderText("🔍 Search artists or songs...")
        self.search_bar.setStyleSheet("padding: 5px; border-radius: 4px; background-color: #313244; color: #cdd6f4;")
        self.search_bar.textChanged.connect(self._filter_library)
        layout.addWidget(self.search_bar)

        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["Artist / Title", "Tracks"])
        self.tree.setColumnWidth(0, 180)
        self.tree.itemDoubleClicked.connect(self._on_item_double_clicked)
        layout.addWidget(self.tree)

        self.refresh_library()

    def refresh_library(self):
        self.tree.clear()
        artist_counts = self.db.get_tracks_per_artist()
        all_tracks = self.db.get_all_tracks()

        total_songs = sum(count for _, count in artist_counts)
        self.summary_label.setText(f"Artists: {len(artist_counts)} | Total Songs: {total_songs}")

        for artist, count in artist_counts:
            artist_item = QTreeWidgetItem(self.tree, [f"👤 {artist}", f"{count} song{'s' if count != 1 else ''}"])
            artist_tracks = [t for t in all_tracks if (t[2] or 'Unknown Artist') == artist]
            for t_id, title, _, file_path in artist_tracks:
                track_title = title if title else "Untitled Track"
                track_item = QTreeWidgetItem(artist_item, [f"🎵 {track_title}", ""])
                track_item.setData(0, 256, file_path)
                
        if self.search_bar.text():
            self._filter_library(self.search_bar.text())

    def _filter_library(self, text):
        text = text.lower()
        for i in range(self.tree.topLevelItemCount()):
            artist_item = self.tree.topLevelItem(i)
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
                if text:  # Expand the folder automatically if searching
                    artist_item.setExpanded(True)
            else:
                artist_item.setHidden(True)

    def _on_item_double_clicked(self, item, column):
        file_path = item.data(0, 256)
        if file_path:
            self.play_requested.emit(file_path)
