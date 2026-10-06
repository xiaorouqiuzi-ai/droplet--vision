from ..i18n import tr, current_language
from PySide6.QtGui import QIcon, QPixmap, QColor
from ...annotations.display_style import label_color, ordered_ids, record_ordinals
from ..widgets.wrapped_label import WrappedLabel
from PySide6.QtCore import Qt, Signal, QSignalBlocker
from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel, QListWidget, QGroupBox, QButtonGroup, QToolButton, QSizePolicy


class AnnotationPanel(QWidget):
    label_changed = Signal()
    annotation_selected = Signal(object)

    def __init__(self, labels, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        self.taxonomy = {label.label_id: label for label in labels}
        layout.setContentsMargins(0, 0, 0, 0)
        labels_group = self.labels_group = QGroupBox(tr('Object Annotation'))
        labels_layout = QVBoxLayout(labels_group)
        layout.addWidget(labels_group)
        self.labels = QListWidget()
        for label in labels:
            if label.enabled:
                self.labels.addItem(tr(label.display_name))
                self.labels.item(self.labels.count() - 1).setData(Qt.ItemDataRole.UserRole, label.label_id)
        self.labels.hide()  # Selection model retained for keyboard/tests; buttons are the UI.
        self.button_host = QWidget()
        self.button_layout = QVBoxLayout(self.button_host)
        self.button_layout.setContentsMargins(0,0,0,0)
        self.button_layout.setSpacing(3)
        labels_layout.addWidget(self.button_host)
        self.object_buttons = {}
        self.button_group = QButtonGroup(self)
        self.button_group.setExclusive(True)
        self.display_config = {"palette":["#808080"], "object_styles":{}}
        self.selected = QLabel(tr("Selected label: none"))
        self.selected.setWordWrap(True)
        self.selected.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.labels.currentItemChanged.connect(self._label_selected)
        labels_layout.addWidget(self.selected)
        self.tool_host = QWidget()
        QVBoxLayout(self.tool_host).setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.tool_host)
        self.records_group = QGroupBox(tr('Current frame annotations'))
        self.records_group.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Maximum)
        records_layout = QVBoxLayout(self.records_group)
        layout.addWidget(self.records_group)
        self.count = WrappedLabel(tr("Current frame annotations: 0"))
        records_layout.addWidget(self.count)
        self.items = QListWidget()
        self.items.setWordWrap(True)
        self.items.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.items.setFixedHeight(100)
        self.items.currentItemChanged.connect(lambda current, previous: self.annotation_selected.emit(
            current.data(Qt.ItemDataRole.UserRole) if current else None))
        records_layout.addWidget(self.items)
        self.details = QLabel(tr("No annotation selected"))
        self.details.setWordWrap(True)
        self.details.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        # The editor places selection details in the Select tool settings page.

    def _label_selected(self, current, previous):
        self.retranslate()
        self.label_changed.emit()

    def label_name(self, label):
        return self.display_config.get('object_display_names', {}).get(label.label_id, {}).get(
            current_language(), tr(label.display_name))

    def retranslate(self):
        # Do not emit label_changed: it cancels the current drawing draft.
        label = self.selected_label()
        self.selected.setText(tr('Current label: {label}').format(label=self.label_name(label)) +
                              '\nID: ' + label.label_id if label else tr('Selected label: none'))
        for key, button in self.object_buttons.items():
            button.setChecked(label is not None and label.label_id == key)
            button.setText(self.label_name(self.taxonomy[key]))
        with QSignalBlocker(self.labels):
            for i in range(self.labels.count()):
                item = self.labels.item(i)
                item.setText(self.label_name(self.taxonomy[item.data(Qt.ItemDataRole.UserRole)]))

    def selected_label(self):
        item = self.labels.currentItem()
        return self.taxonomy.get(item.data(Qt.ItemDataRole.UserRole)) if item else None

    def configure_display(self, display):
        self.display_config = display
        selected = self.selected_label()
        key = selected.label_id if selected else None
        ids = ordered_ids(list(self.taxonomy), display.get("object_order", []))
        self.replace_labels([self.taxonomy[k] for k in ids], key)

    def replace_labels(self, labels, selected_id=None):
        blocker = QSignalBlocker(self.labels)
        self.taxonomy = {label.label_id: label for label in labels}
        self.labels.clear()
        for label in labels:
            if label.enabled:
                self.labels.addItem(tr(label.display_name))
                self.labels.item(self.labels.count()-1).setData(Qt.ItemDataRole.UserRole, label.label_id)
        while self.button_layout.count():
            widget = self.button_layout.takeAt(0).widget()
            self.button_group.removeButton(widget)
            widget.deleteLater()
        self.object_buttons.clear()
        for label in labels:
            button = QToolButton()
            button.setText(self.label_name(label))
            button.setStyleSheet('QToolButton:checked { border: 2px solid palette(highlight); font-weight: bold; }')
            button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
            button.setCheckable(True)
            button.setEnabled(label.enabled)
            button.setToolTip(label.label_id)
            button.setIcon(color_icon(label_color(self.display_config, label.label_id)))
            self.button_group.addButton(button)
            self.button_layout.addWidget(button)
            self.object_buttons[label.label_id] = button
            button.clicked.connect(lambda checked=False, key=label.label_id: self.select_label_id(key))
        row = next((i for i in range(self.labels.count()) if self.labels.item(i).data(Qt.ItemDataRole.UserRole)==selected_id),0)
        self.labels.setCurrentRow(row if self.labels.count() else -1)
        del blocker
        self._label_selected(None, None)

    def select_label_id(self, key):
        for i in range(self.labels.count()):
            if self.labels.item(i).data(Qt.ItemDataRole.UserRole) == key:
                self.labels.setCurrentRow(i)
                break

    def set_records(self, records, colors=None):
        self.count.setText(tr("Current frame annotations: ") + str(len(records)))
        blocker = QSignalBlocker(self.items)
        self.items.clear()
        ordinals = record_ordinals(records)
        for record in records:
            label = self.taxonomy.get(record.label_id)
            name = self.label_name(label) if label else tr('Unknown / Legacy') + ': ' + record.label_id
            instance = record.attributes.get('instance_name', '')
            title = f"{instance} · {name}" if instance else name
            if record.label_id == 'daughter_droplet':
                title += f' #{ordinals[record.annotation_id]}'
            self.items.addItem(f"{title}\n{record.geometry_type} · {record.source}")
            item = self.items.item(self.items.count()-1)
            item.setData(Qt.ItemDataRole.UserRole, record.annotation_id)
            color = (colors or {}).get(record.annotation_id, label_color(self.display_config, record.label_id))
            item.setIcon(color_icon(color))
            item.setData(Qt.ItemDataRole.UserRole + 1, color)
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


def color_icon(color):
    pixmap = QPixmap(12,12)
    pixmap.fill(QColor(color))
    return QIcon(pixmap)
