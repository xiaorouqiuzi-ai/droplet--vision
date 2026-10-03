"""Lightweight queue view. Paths and transitions belong to QueueCoordinator."""
from PySide6.QtCore import Signal, Qt
from PySide6.QtWidgets import QWidget, QVBoxLayout, QGridLayout, QPushButton, QLabel, QListWidget, QListWidgetItem


class QueuePanel(QWidget):
    requested = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        self.heading = QLabel("Queue: none")
        self.progress = QLabel("0 / 0 done")
        self.current = QLabel("Current item: none")
        self.current.setWordWrap(True)
        self.root_label = QLabel("Dataset root: not set (local only)")
        self.root_label.setWordWrap(True)
        for widget in (self.heading, self.progress, self.current, self.root_label):
            layout.addWidget(widget)
        buttons = QGridLayout()
        self.buttons = {}
        actions = [("open_queue", "Open Queue..."), ("set_root", "Set Dataset Root..."),
                   ("open_item", "Open Selected Item"), ("save", "Save Queue"),
                   ("previous", "Previous Pending"), ("next", "Next Pending"),
                   ("done", "Mark Done"), ("skipped", "Mark Skipped"),
                   ("review", "Mark Needs Review"), ("note", "Add Note")]
        for index, (key, text) in enumerate(actions):
            button = QPushButton(text)
            button.clicked.connect(lambda checked=False, action=key: self.requested.emit(action))
            buttons.addWidget(button, index//2, index%2)
            self.buttons[key] = button
        layout.addLayout(buttons)
        self.items = QListWidget()
        self.items.setMinimumWidth(280)
        self.items.itemDoubleClicked.connect(lambda item: self.requested.emit("open_item"))
        layout.addWidget(self.items)

    def selected_id(self):
        item = self.items.currentItem()
        return item.data(Qt.ItemDataRole.UserRole) if item is not None else None

    def show_queue(self, queue, current_id=None, unavailable=None):
        selected = self.selected_id()
        self.items.clear()
        self.heading.setText("Queue: " + queue.name + (" *" if queue.dirty else ""))
        self.progress.setText(f"{queue.done_count} / {len(queue.items)} done")
        for row in queue.items:
            prefix = "UNAVAILABLE / " if row.item_id in (unavailable or {}) else ""
            item = QListWidgetItem(f"{prefix}{row.status} | {row.cine_filename} | {row.frame_index} | {', '.join(row.sample_reasons)}")
            item.setData(Qt.ItemDataRole.UserRole, row.item_id)
            item.setToolTip(row.relative_cine_path + "\n" + row.notes + "\n" + (unavailable or {}).get(row.item_id, ""))
            self.items.addItem(item)
            if row.item_id == selected:
                self.items.setCurrentItem(item)
        if current_id:
            row = queue.get(current_id)
            self.current.setText(f"Current item: {row.cine_filename} / frame {row.frame_index} ({row.status})")
        else:
            self.current.setText("Current item: none")
