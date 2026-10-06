"""Selectable, label-like text using Qt's anywhere-capable document wrapping.

QLabel's plain-text layout can clip long unbroken Windows paths. QTextBrowser
retains the exact text (including clipboard/accessibility), without inserting
zero-width characters or serializing any display formatting.
"""
from math import ceil
from PySide6.QtCore import Qt, QSize
from PySide6.QtGui import QTextOption, QTextDocument
from PySide6.QtWidgets import QTextBrowser, QSizePolicy, QFrame


class WrappedLabel(QTextBrowser):
    def __init__(self, text='', parent=None):
        super().__init__(parent)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setStyleSheet('QTextBrowser { background: transparent; border: none; }')
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.setWordWrap(True)
        policy = QSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        policy.setHeightForWidth(True)
        self.setSizePolicy(policy)
        self.document().setDocumentMargin(0)
        self.setText(text)

    def setTextFormat(self, value):
        pass  # Values always use plain text, never interpret HTML from a path.

    def setWordWrap(self, enabled):
        self.setWordWrapMode(QTextOption.WrapMode.WrapAtWordBoundaryOrAnywhere if enabled
                            else QTextOption.WrapMode.NoWrap)

    def wordWrap(self):
        return self.wordWrapMode() != QTextOption.WrapMode.NoWrap

    def setText(self, text):
        self.setPlainText(str(text))
        self._size_to_text()
        self.updateGeometry()

    def text(self):
        return self.toPlainText()

    def heightForWidth(self, width):
        doc = QTextDocument()
        doc.setDefaultFont(self.font())
        doc.setDocumentMargin(0)
        option = doc.defaultTextOption()
        option.setWrapMode(self.wordWrapMode())
        doc.setDefaultTextOption(option)
        doc.setPlainText(self.text() or ' ')
        doc.setTextWidth(max(1, width-2))
        return ceil(doc.size().height()) + 2

    def minimumSizeHint(self):
        return QSize(0, self.fontMetrics().height()+2)

    def sizeHint(self):
        return QSize(150, self.heightForWidth(150))

    def _size_to_text(self):
        self.setFixedHeight(self.heightForWidth(self.width()))

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._size_to_text()
