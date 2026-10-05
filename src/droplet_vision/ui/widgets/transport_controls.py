from ..i18n import tr
from PySide6.QtCore import Signal
from PySide6.QtWidgets import QWidget, QHBoxLayout, QPushButton, QComboBox, QLabel

REVIEW_PLAYBACK_FPS = (1, 2, 5, 10, 15, 20, 30, 1000)


class TransportControls(QWidget):
    step = Signal(int)
    first = Signal()
    last = Signal()
    toggle_play = Signal()
    fps_changed = Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QHBoxLayout(self)
        self.frame_step = QComboBox()
        self.frame_step.setObjectName('frameStep')
        for value in (1, 10, 100, 1000):
            self.frame_step.addItem(tr('{count} frames').format(count=value), value)
        self.previous = QPushButton('<')
        self.next = QPushButton('>')
        self.previous.setToolTip(tr('Previous by selected frame step'))
        self.next.setToolTip(tr('Next by selected frame step'))
        self.previous.clicked.connect(lambda: self.step.emit(-self.frame_step.currentData()))
        self.next.clicked.connect(lambda: self.step.emit(self.frame_step.currentData()))
        first, last = QPushButton('|<'), QPushButton('>|')
        first.clicked.connect(self.first.emit)
        last.clicked.connect(self.last.emit)
        for button in (first, self.previous, self.next, last):
            button.setMaximumWidth(45)
            layout.addWidget(button)
        layout.addWidget(QLabel(tr('Frame step')))
        layout.addWidget(self.frame_step)
        self.play = QPushButton(tr("Play"))
        self.play.clicked.connect(self.toggle_play.emit)
        layout.addWidget(self.play)
        layout.addWidget(QLabel(tr("Review playback FPS")))
        self.fps = QComboBox()
        self.fps.addItems([str(fps) for fps in REVIEW_PLAYBACK_FPS])
        self.fps.setToolTip(tr('Target review playback rate; actual speed depends on decoding and rendering.'))
        self.fps.setCurrentText("10")
        self.fps.currentTextChanged.connect(lambda value: self.fps_changed.emit(int(value)))
        layout.addWidget(self.fps)
