from ..i18n import tr
from PySide6.QtCore import Signal
from PySide6.QtWidgets import QWidget, QHBoxLayout, QVBoxLayout, QPushButton, QComboBox, QLabel, QStyle

REVIEW_PLAYBACK_FPS = (1, 2, 5, 10, 15, 20, 30, 60, 120, 240, 500, 1000)


class TransportControls(QWidget):
    step = Signal(int)
    first = Signal()
    last = Signal()
    toggle_play = Signal()
    fps_changed = Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        navigation = QHBoxLayout()
        layout.addLayout(navigation)
        self.jump_buttons = {}
        self.frame_label = QLabel('0 / 0')
        for delta in (-1000, -100, -10, -1, 1, 10, 100, 1000):
            if delta == 1:
                navigation.addWidget(self.frame_label, 1)
            button = QPushButton(f'{delta:+d}')
            button.setToolTip(tr('Jump {delta} frames').format(delta=f'{delta:+d}'))
            button.clicked.connect(lambda checked=False, value=delta: self.step.emit(value))
            navigation.addWidget(button)
            self.jump_buttons[delta] = button
        self.previous, self.next = self.jump_buttons[-1], self.jump_buttons[1]
        playback = QHBoxLayout()
        layout.addLayout(playback)
        self.play = QPushButton(tr('Play'))
        self.play.clicked.connect(self.toggle_play.emit)
        playback.addWidget(self.play)
        playback.addWidget(QLabel(tr('Review Speed (frames/s)')))
        self.fps = QComboBox()
        self.fps.addItems([str(fps) for fps in REVIEW_PLAYBACK_FPS])
        self.fps.setToolTip(tr('Source frames advanced per real second; not experimental FPS. High-speed review may skip intermediate frames to maintain the requested scan rate.'))
        self.fps.setCurrentText('10')
        self.fps.currentTextChanged.connect(lambda value: self.fps_changed.emit(int(value)))
        playback.addWidget(self.fps)
        playback.addStretch()
        self.save_package = QPushButton(tr('Save Annotation Package'))
        self.save_package.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_DialogSaveButton))
        self.save_package.setToolTip(tr('Save changes to the currently opened annotation package'))
        self.save_package.setStyleSheet('QPushButton { border: 1px solid palette(highlight); padding: 5px 12px; }')
        self.save_package.hide()
        playback.addWidget(self.save_package)
