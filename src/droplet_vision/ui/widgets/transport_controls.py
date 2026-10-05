from ..i18n import tr
from PySide6.QtCore import Signal
from PySide6.QtWidgets import QWidget, QHBoxLayout, QPushButton, QComboBox, QLabel


class TransportControls(QWidget):
    step = Signal(int)
    first = Signal()
    last = Signal()
    toggle_play = Signal()
    fps_changed = Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QHBoxLayout(self)
        for text, callback in [("|<", self.first.emit), ("<<", lambda: self.step.emit(-10)),
                               ("<", lambda: self.step.emit(-1)), (">", lambda: self.step.emit(1)),
                               (">>", lambda: self.step.emit(10)), (">|", self.last.emit)]:
            button = QPushButton(text)
            button.clicked.connect(callback)
            layout.addWidget(button)
        self.play = QPushButton(tr("Play"))
        self.play.clicked.connect(self.toggle_play.emit)
        layout.addWidget(self.play)
        layout.addWidget(QLabel(tr("Review playback FPS")))
        self.fps = QComboBox()
        self.fps.addItems(["1", "2", "5", "10", "15", "20", "30"])
        self.fps.setCurrentText("10")
        self.fps.currentTextChanged.connect(lambda value: self.fps_changed.emit(int(value)))
        layout.addWidget(self.fps)
