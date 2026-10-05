from ..i18n import tr
from PySide6.QtCore import Qt, Signal, QTimer, QSignalBlocker
from PySide6.QtWidgets import QWidget, QSlider, QSpinBox, QHBoxLayout, QLabel


class Timeline(QWidget):
    requested = Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.slider = QSlider(Qt.Orientation.Horizontal)
        self.slider.setObjectName("frameSlider")
        self.spinbox = QSpinBox()
        self.spinbox.setObjectName("frameSpinbox")
        self.end_label = QLabel("/ 0")
        layout = QHBoxLayout(self)
        layout.addWidget(QLabel(tr("Frame")))
        layout.addWidget(self.slider, 1)
        layout.addWidget(self.spinbox)
        layout.addWidget(self.end_label)
        self.debounce = QTimer(self)
        self.debounce.setSingleShot(True)
        self.debounce.setInterval(50)
        self.debounce.timeout.connect(lambda: self.requested.emit(self.slider.value()))
        self.slider.valueChanged.connect(self._slide)
        self.spinbox.valueChanged.connect(self._spin)
        self.set_count(0)

    def _slide(self, value):
        with QSignalBlocker(self.spinbox):
            self.spinbox.setValue(value)
        self.debounce.start()

    def _spin(self, value):
        self.debounce.stop()
        with QSignalBlocker(self.slider):
            self.slider.setValue(value)
        self.requested.emit(value)

    def set_count(self, count):
        self.debounce.stop()
        with QSignalBlocker(self.slider), QSignalBlocker(self.spinbox):
            self.slider.setRange(0, max(0, count - 1))
            self.spinbox.setRange(0, max(0, count - 1))
        self.end_label.setText("/ " + str(max(0, count - 1)))
        self.setEnabled(count > 0)

    def set_frame(self, value):
        self.debounce.stop()
        with QSignalBlocker(self.slider), QSignalBlocker(self.spinbox):
            self.slider.setValue(value)
            self.spinbox.setValue(value)
