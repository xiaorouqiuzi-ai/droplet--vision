"""Human-controlled temporary selection settings, never scientific metadata."""
from ..i18n import tr
from PySide6.QtCore import Signal, Qt
from PySide6.QtWidgets import QWidget, QFormLayout, QSlider, QComboBox, QLabel, QPushButton, QHBoxLayout
from ...annotations.magic_wand import load_wand_config


class MagicWandPanel(QWidget):
    changed = Signal()
    confirm_requested = Signal()
    cancel_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.config = load_wand_config()
        layout = QFormLayout(self)
        self.tolerance = QSlider(Qt.Orientation.Horizontal)
        self.tolerance.setRange(self.config.min_tolerance, self.config.max_tolerance)
        self.tolerance.setValue(self.config.default_tolerance)
        self.tolerance_label = QLabel()
        layout.addRow(self.tolerance_label, self.tolerance)
        self.connectivity = QComboBox()
        for value in (4, 8):
            self.connectivity.addItem(str(value), value)
        self.connectivity.setCurrentIndex(self.connectivity.findData(self.config.connectivity))
        layout.addRow(tr('Connectivity'), self.connectivity)
        self.mode = QComboBox()
        for label, key in [(tr('Replace'),'replace'),(tr('Add'),'add'),(tr('Subtract'),'subtract')]:
            self.mode.addItem(label, key)
        layout.addRow(tr('Selection operation'), self.mode)
        self.hint = QLabel(tr('Click a target region to select similar grayscale pixels.'))
        self.hint.setWordWrap(True)
        layout.addRow(self.hint)
        buttons = QHBoxLayout()
        self.confirm_button = QPushButton(tr('Confirm selection'))
        self.confirm_button.setEnabled(False)
        self.cancel_button = QPushButton(tr('Cancel'))
        buttons.addWidget(self.confirm_button)
        buttons.addWidget(self.cancel_button)
        layout.addRow(buttons)
        self.confirm_button.clicked.connect(self.confirm_requested.emit)
        self.cancel_button.clicked.connect(self.cancel_requested.emit)
        self.tolerance.valueChanged.connect(self._changed)
        self.connectivity.currentIndexChanged.connect(self._changed)
        self._changed()

    def _changed(self):
        self.tolerance_label.setText(tr('Tolerance: ') + str(self.tolerance.value()))
        self.changed.emit()
