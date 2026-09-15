from PySide6.QtWidgets import QWidget, QVBoxLayout, QTreeWidget, QTreeWidgetItem, QLabel
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

    def _on_item_double_clicked(self, item, column):
        file_path = item.data(0, 256)
        if file_path:
            self.play_requested.emit(file_path)
