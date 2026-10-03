from PySide6.QtCore import Qt, Signal, QSignalBlocker
from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel, QListWidget


class AnnotationPanel(QWidget):
    label_changed = Signal()
    annotation_selected = Signal(object)

    def __init__(self, labels, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        self.taxonomy = {label.label_id: label for label in labels}
        layout.addWidget(QLabel("Taxonomy"))
        self.labels = QListWidget()
        for label in labels:
            if label.enabled:
                self.labels.addItem(label.display_name)
                self.labels.item(self.labels.count() - 1).setData(Qt.ItemDataRole.UserRole, label.label_id)
        layout.addWidget(self.labels)
        self.labels.setMaximumHeight(120)
        self.selected = QLabel("Selected label: none")
        self.labels.currentItemChanged.connect(lambda current, previous: self.selected.setText(
            "Selected label: " + (current.data(Qt.ItemDataRole.UserRole) if current else "none")))
        self.labels.currentItemChanged.connect(lambda *_: self.label_changed.emit())
        layout.addWidget(self.selected)
        self.count = QLabel("Current frame annotations: 0")
        layout.addWidget(self.count)
        self.items = QListWidget()
        self.items.setMaximumHeight(140)
        self.items.currentItemChanged.connect(lambda current, previous: self.annotation_selected.emit(
            current.data(Qt.ItemDataRole.UserRole) if current else None))
        layout.addWidget(self.items)
        self.details = QLabel("No annotation selected")
        self.details.setWordWrap(True)
        self.details.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(self.details)

    def selected_label(self):
        item = self.labels.currentItem()
        return self.taxonomy.get(item.data(Qt.ItemDataRole.UserRole)) if item else None

    def set_records(self, records):
        self.count.setText("Current frame annotations: " + str(len(records)))
        blocker = QSignalBlocker(self.items)
        self.items.clear()
        for record in records:
            label = self.taxonomy.get(record.label_id)
            name = label.display_name if label else record.label_id
            self.items.addItem(f"{name} · {record.geometry_type} · {record.source}")
            self.items.item(self.items.count()-1).setData(Qt.ItemDataRole.UserRole, record.annotation_id)
        del blocker

    def select_record(self, record):
        blocker = QSignalBlocker(self.items)
        self.items.setCurrentRow(-1)
        if record is None:
            self.details.setText("No annotation selected")
        else:
            for i in range(self.items.count()):
                if self.items.item(i).data(Qt.ItemDataRole.UserRole) == record.annotation_id:
                    self.items.setCurrentRow(i)
                    break
            self.details.setText(f"Label: {record.label_id}\nGeometry: {record.geometry_type}\n"
                                 f"ID: {record.annotation_id}\nSource: {record.source}\n"
                                 f"Review: {record.review_status}\nModel: {record.model_id}\n"
                                 f"Confidence: {record.confidence}\nDerived from: {record.derived_from}")
        del blocker
