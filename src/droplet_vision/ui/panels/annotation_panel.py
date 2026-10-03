from PySide6.QtCore import Qt
from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel, QListWidget


class AnnotationPanel(QWidget):
    def __init__(self, labels, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Taxonomy"))
        self.labels = QListWidget()
        for label in labels:
            if label.enabled:
                self.labels.addItem(label.display_name)
                self.labels.item(self.labels.count() - 1).setData(Qt.ItemDataRole.UserRole, label.label_id)
        layout.addWidget(self.labels)
        self.selected = QLabel("Selected label: none")
        self.labels.currentItemChanged.connect(lambda current, previous: self.selected.setText(
            "Selected label: " + (current.data(Qt.ItemDataRole.UserRole) if current else "none")))
        layout.addWidget(self.selected)
        self.count = QLabel("Current frame annotations: 0")
        layout.addWidget(self.count)
        self.items = QListWidget()
        layout.addWidget(self.items)

    def set_records(self, records):
        self.count.setText("Current frame annotations: " + str(len(records)))
        self.items.clear()
        for record in records:
            self.items.addItem(f"{record.label_id} · {record.geometry_type} · {record.review_status}")
