from ..i18n import tr, current_language
from PySide6.QtGui import QIcon, QPixmap, QColor, QPainter, QPen
from ...annotations.display_style import label_color, ordered_ids, record_ordinals
from ..widgets.wrapped_label import WrappedLabel
from PySide6.QtCore import Qt, Signal, QSignalBlocker
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QListWidget, QGroupBox, QButtonGroup, QToolButton, QSizePolicy, QMenu


class AnnotationPanel(QWidget):
    label_changed = Signal()
    annotation_selected = Signal(object)
    visibility_changed = Signal(str, bool)
    delete_requested = Signal(str)

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
        self.eye_buttons = {}
        self.projection_ids = set()
        self.can_delete = lambda key: False
        self.items.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.items.customContextMenuRequested.connect(self.show_context_menu)
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
        name = self.display_config.get('object_display_names', {}).get(label.label_id, {}).get(
            current_language(), tr(label.display_name))
        # Old frozen package/scheme snapshots keep their stored provenance.
        if label.label_id == 'support_structure' and name in ('Support structure', '支撑结构'):
            return tr('Droplet support rod')
        return name

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

    def set_records(self, records, colors=None, hidden=(), projections=()):
        self.projection_ids = set(projections)
        self.count.setText(tr('Frame annotations: {count} | Templates: {templates}').format(
            count=len(records)-len(projections), templates=len(projections)))
        blocker = QSignalBlocker(self.items)
        self.items.clear()
        self.eye_buttons.clear()
        ordinals = record_ordinals(records)
        template_numbers = {record.annotation_id: index for index, record in enumerate(
            (record for record in records if record.annotation_id in projections), 1)}
        for record in records:
            label = self.taxonomy.get(record.label_id)
            name = self.label_name(label) if label else tr('Unknown / Legacy') + ': ' + record.label_id
            instance = record.attributes.get('instance_name', '')
            title = f"{instance} · {name}" if instance else name
            if not instance and record.annotation_id in template_numbers:
                title += f' {template_numbers[record.annotation_id]}'
            if record.label_id == 'daughter_droplet':
                title += f' #{ordinals[record.annotation_id]}'
            detail = tr('Package template' if record.attributes.get('template_scope') == 'package' else 'Cine template') if record.annotation_id in projections else (
                tr('Frame override') if record.attributes.get('creation_tool') in ('cine_support_template_override', 'package_support_template_override') else record.source)
            text = f"{title}\n{record.geometry_type} · {detail}"
            offset = record.attributes.get('frame_translation')
            if offset and record.attributes.get('creation_tool') in ('cine_template_projection', 'package_template_projection'):
                text += '\n' + tr('Offset ({dx:+.3f}, {dy:+.3f})').format(**offset)
            self.items.addItem(text)
            item = self.items.item(self.items.count()-1)
            item.setData(Qt.ItemDataRole.UserRole, record.annotation_id)
            color = (colors or {}).get(record.annotation_id, label_color(self.display_config, record.label_id))
            item.setIcon(color_icon(color))
            item.setData(Qt.ItemDataRole.UserRole + 1, color)
            row = QWidget()
            row.setAutoFillBackground(True)
            layout = QHBoxLayout(row)
            layout.setContentsMargins(3,2,3,2)
            title_label = QLabel(text)
            title_label.setWordWrap(True)
            title_label.setMinimumWidth(0)
            title_label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
            layout.addWidget(title_label, 1)
            eye = QToolButton()
            eye.setCheckable(True)
            eye.setChecked(record.annotation_id not in hidden)
            eye.setIcon(visibility_icon(eye.isChecked(), self.palette().text().color()))
            eye.setToolTip(tr('Visible') if eye.isChecked() else tr('Hidden'))
            eye.setAccessibleName(tr('Visible') + ': ' + title)
            eye.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            eye.clicked.connect(lambda checked, key=record.annotation_id: self.visibility_changed.emit(key, checked))
            layout.addWidget(eye)
            self.eye_buttons[record.annotation_id] = eye
            item.setSizeHint(row.sizeHint())
            self.items.setItemWidget(item, row)
        del blocker

    def context_menu(self, annotation_id):
        menu = QMenu(self)
        if annotation_id in self.projection_ids:
            menu.addAction(tr('Hide this template'), lambda: self.visibility_changed.emit(annotation_id, False))
        else:
            action = menu.addAction(tr('Delete Annotation'), lambda: self.delete_requested.emit(annotation_id))
            action.setEnabled(self.can_delete(annotation_id))
        if hasattr(self, 'support_actions'):
            self.support_actions(menu, annotation_id)
        return menu

    def show_context_menu(self, position):
        item = self.items.itemAt(position)
        if item is not None:
            menu = self.context_menu(item.data(Qt.ItemDataRole.UserRole))
            menu.exec(self.items.viewport().mapToGlobal(position))
            menu.deleteLater()

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

        for i in range(self.items.count()):
            item = self.items.item(i)
            row = self.items.itemWidget(item)
            if row is not None:
                row.setStyleSheet('background: palette(highlight); color: palette(highlighted-text);'
                                 if item.isSelected() else '')


def color_icon(color):
    pixmap = QPixmap(12,12)
    pixmap.fill(QColor(color))
    return QIcon(pixmap)


def visibility_icon(visible, color):
    pixmap = QPixmap(18,18)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setPen(QPen(color, 1.5))
    painter.drawEllipse(1,5,16,8)
    painter.setBrush(color)
    painter.drawEllipse(7,7,4,4)
    if not visible:
        painter.drawLine(2,2,16,16)
    painter.end()
    return QIcon(pixmap)
