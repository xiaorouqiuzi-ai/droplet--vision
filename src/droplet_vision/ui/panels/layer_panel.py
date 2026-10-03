from PySide6.QtCore import Signal
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QCheckBox, QLabel


class LayerPanel(QWidget):
    changed = Signal()

    def __init__(self, layers, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Layers"))
        for layer in layers:
            row = QHBoxLayout()
            visible = QCheckBox(layer.name)
            visible.setChecked(layer.visible)
            lock = QCheckBox("Locked")
            lock.setChecked(layer.locked)
            visible.toggled.connect(lambda checked, item=layer: self._set(item, "visible", checked))
            lock.toggled.connect(lambda checked, item=layer: self._set(item, "locked", checked))
            row.addWidget(visible)
            row.addWidget(lock)
            layout.addLayout(row)

    def _set(self, layer, key, value):
        setattr(layer, key, value)
        self.changed.emit()
