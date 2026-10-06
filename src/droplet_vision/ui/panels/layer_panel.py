from ..i18n import tr
from PySide6.QtCore import Signal
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QCheckBox, QLabel, QComboBox


class LayerPanel(QWidget):
    changed = Signal()

    def __init__(self, layers, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(tr("Layers")))
        self.layers = layers
        self.active_layer = QComboBox()
        self.drawing_into = QLabel(tr("Drawing into: Manual"))
        for layer in layers:
            self.active_layer.addItem(tr(layer.name), layer.layer_id)
        self.active_layer.currentIndexChanged.connect(self._active_changed)
        layout.addWidget(self.active_layer)
        layout.addWidget(self.drawing_into)
        for layer in layers:
            row = QHBoxLayout()
            visible = QCheckBox(tr(layer.name))
            visible.setChecked(layer.visible)
            lock = QCheckBox(tr("Locked"))
            lock.setChecked(layer.locked)
            visible.toggled.connect(lambda checked, item=layer: self._set(item, "visible", checked))
            lock.toggled.connect(lambda checked, item=layer: self._set(item, "locked", checked))
            row.addWidget(visible)
            row.addWidget(lock)
            layout.addLayout(row)
        self._update_choices()

    def _active_changed(self):
        self.drawing_into.setText(tr("Drawing into: ") + self.active_layer.currentText())
        self.changed.emit()

    def _update_choices(self):
        for index, layer in enumerate(self.layers):
            item = self.active_layer.model().item(index)
            if item is not None:
                item.setEnabled(not layer.locked and layer.role in ("manual", "reviewed"))

    def _set(self, layer, key, value):
        setattr(layer, key, value)
        self._update_choices()
        self.changed.emit()
