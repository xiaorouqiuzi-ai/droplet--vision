"""Lightweight queue view. Paths and transitions belong to QueueCoordinator."""
from ..i18n import tr
from PySide6.QtCore import Signal, Qt
from PySide6.QtWidgets import QWidget, QVBoxLayout, QGridLayout, QPushButton, QLabel, QListWidget, QListWidgetItem


class QueuePanel(QWidget):
    requested = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        self.heading = QLabel(tr("Queue: none"))
        self.progress = QLabel(tr("0 / 0 done"))
        self.current = QLabel(tr("Current item: none"))
        self.current.setWordWrap(True)
        self.root_label = QLabel(tr("Dataset root: not set (local only)"))
        self.root_label.setWordWrap(True)
        for widget in (self.heading, self.progress, self.current, self.root_label):
            layout.addWidget(widget)
        buttons = QGridLayout()
        self.buttons = {}
        actions = [("open_queue", tr("Open Queue...")), ("set_root", tr("Set Dataset Root...")),
                   ("open_item", tr("Open Selected Item")), ("save", tr("Save Queue")),
                   ("previous", tr("Previous Pending")), ("next", tr("Next Pending")),
                   ("done", tr("Mark Done")), ("skipped", tr("Mark Skipped")),
                   ("review", tr("Mark Needs Review")), ("note", tr("Add Note"))]
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
        self.heading.setText(tr("Queue: ") + queue.name + (" *" if queue.dirty else ""))
        self.progress.setText(tr(f"{queue.done_count} / {len(queue.items)} done"))
        for row in queue.items:
            prefix = "UNAVAILABLE / " if row.item_id in (unavailable or {}) else ""
            item = QListWidgetItem(f"{prefix}{tr(row.status)} | {row.cine_filename} | {row.frame_index} | {', '.join(row.sample_reasons)}")
            item.setData(Qt.ItemDataRole.UserRole, row.item_id)
            item.setToolTip(row.relative_cine_path + "\n" + row.notes + "\n" + (unavailable or {}).get(row.item_id, ""))
            self.items.addItem(item)
            if row.item_id == selected:
                self.items.setCurrentItem(item)
        if current_id:
            row = queue.get(current_id)
            self.current.setText(tr(f"Current item: {row.cine_filename} / frame {row.frame_index} ({row.status})"))
        else:
            self.current.setText(tr("Current item: none"))
