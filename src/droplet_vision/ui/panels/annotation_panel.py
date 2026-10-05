from ..i18n import tr
from PySide6.QtCore import Qt, Signal, QSignalBlocker
from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel, QListWidget, QGroupBox


class AnnotationPanel(QWidget):
    label_changed = Signal()
    annotation_selected = Signal(object)

    def __init__(self, labels, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        self.taxonomy = {label.label_id: label for label in labels}
        layout.setContentsMargins(0, 0, 0, 0)
        labels_group = QGroupBox(tr('Taxonomy'))
        labels_layout = QVBoxLayout(labels_group)
        layout.addWidget(labels_group)
        self.labels = QListWidget()
        for label in labels:
            if label.enabled:
                self.labels.addItem(tr(label.display_name))
                self.labels.item(self.labels.count() - 1).setData(Qt.ItemDataRole.UserRole, label.label_id)
        labels_layout.addWidget(self.labels)
        self.labels.setFixedHeight(132)
        self.selected = QLabel(tr("Selected label: none"))
        self.selected.setWordWrap(True)
        self.selected.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.labels.currentItemChanged.connect(self._label_selected)
        labels_layout.addWidget(self.selected)
        self.tool_host = QWidget()
        QVBoxLayout(self.tool_host).setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.tool_host)
        self.records_group = QGroupBox(tr('Current frame annotations'))
        records_layout = QVBoxLayout(self.records_group)
        layout.addWidget(self.records_group)
        self.count = QLabel(tr("Current frame annotations: 0"))
        records_layout.addWidget(self.count)
        self.items = QListWidget()
        self.items.setFixedHeight(100)
        self.items.currentItemChanged.connect(lambda current, previous: self.annotation_selected.emit(
            current.data(Qt.ItemDataRole.UserRole) if current else None))
        records_layout.addWidget(self.items)
        self.details = QLabel(tr("No annotation selected"))
        self.details.setWordWrap(True)
        self.details.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        # The editor places selection details in the Select tool settings page.

    def _label_selected(self, current, previous):
        label = self.selected_label()
        self.selected.setText(tr('Current label: {label}').format(label=tr(label.display_name)) +
                              '\nID: ' + label.label_id if label else tr('Selected label: none'))
        self.label_changed.emit()

    def selected_label(self):
        item = self.labels.currentItem()
        return self.taxonomy.get(item.data(Qt.ItemDataRole.UserRole)) if item else None

    def set_records(self, records):
        self.count.setText(tr("Current frame annotations: ") + str(len(records)))
        blocker = QSignalBlocker(self.items)
        self.items.clear()
        for record in records:
            label = self.taxonomy.get(record.label_id)
            name = tr(label.display_name) if label else record.label_id
            self.items.addItem(f"{name} · {record.geometry_type} · {record.source}")
            self.items.item(self.items.count()-1).setData(Qt.ItemDataRole.UserRole, record.annotation_id)
        del blocker

    def select_record(self, record):
        blocker = QSignalBlocker(self.items)
        self.items.setCurrentRow(-1)
        if record is None:
            self.details.setText(tr("No annotation selected"))
        else:
            for i in range(self.items.count()):
                if self.items.item(i).data(Qt.ItemDataRole.UserRole) == record.annotation_id:
                    self.items.setCurrentRow(i)
                    break
            self.details.setText(tr(f"Label: {record.label_id}\nGeometry: {record.geometry_type}\n"
                                 f"ID: {record.annotation_id}\nSource: {record.source}\n"
                                 f"Review: {record.review_status}\nModel: {record.model_id}\n"
                                 f"Confidence: {record.confidence}\nDerived from: {record.derived_from}"))
        del blocker
