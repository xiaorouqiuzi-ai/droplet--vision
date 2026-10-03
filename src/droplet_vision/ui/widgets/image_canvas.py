"""Graphics scene in raw image coordinates, ready for editable overlays."""
from PySide6.QtCore import Qt, QRectF
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QGraphicsView, QGraphicsScene, QGraphicsPixmapItem
from ..display import to_qimage
from ..overlays.manager import OverlayManager


class ImageCanvas(QGraphicsView):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setScene(QGraphicsScene(self))
        self.image_item = QGraphicsPixmapItem()
        self.scene().addItem(self.image_item)
        self.overlays = OverlayManager(self.scene())
        self.setBackgroundBrush(Qt.GlobalColor.darkGray)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self._pan_start = None
        self.setMinimumSize(320, 280)
        self.setObjectName("imageCanvas")

    def set_image(self, raw, fit=False):
        first = self.image_item.pixmap().isNull()
        self.image_item.setPixmap(QPixmap.fromImage(to_qimage(raw)))
        h, w = raw.shape[:2]
        self.setSceneRect(QRectF(0, 0, w, h))
        if fit or first:
            self.fit_image()

    def clear_image(self):
        self.overlays.clear()
        self.image_item.setPixmap(QPixmap())

    def fit_image(self):
        if not self.image_item.pixmap().isNull():
            self.fitInView(self.image_item, Qt.AspectRatioMode.KeepAspectRatio)

    def zoom(self, factor):
        current = self.transform().m11()
        if 0.02 <= current * factor <= 100:
            self.scale(factor, factor)

    def wheelEvent(self, event):
        self.zoom(1.2 if event.angleDelta().y() > 0 else 1 / 1.2)
        event.accept()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.MiddleButton:
            self._pan_start = event.position().toPoint()
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
            event.accept()
        else:
            super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._pan_start is not None:
            position = event.position().toPoint()
            delta = position - self._pan_start
            self.horizontalScrollBar().setValue(self.horizontalScrollBar().value() - delta.x())
            self.verticalScrollBar().setValue(self.verticalScrollBar().value() - delta.y())
            self._pan_start = position
            event.accept()
        else:
            super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.MiddleButton:
            self._pan_start = None
            self.unsetCursor()
            event.accept()
        else:
            super().mouseReleaseEvent(event)
