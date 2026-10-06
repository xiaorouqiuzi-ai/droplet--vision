"""Graphics scene in raw image coordinates, ready for editable overlays."""
from PySide6.QtCore import Qt, QRectF, QTimer, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QGraphicsView, QGraphicsScene, QGraphicsPixmapItem, QMenu
from ..i18n import tr
from ..display import to_qimage
from ..overlays.manager import OverlayManager
from ...annotations.geometry import clamp_point


class ImageCanvas(QGraphicsView):
    auto_fit_changed = Signal(bool)
    fitted = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setScene(QGraphicsScene(self))
        self.image_item = QGraphicsPixmapItem()
        self.scene().addItem(self.image_item)
        self.overlays = OverlayManager(self.scene())
        self.setBackgroundBrush(Qt.GlobalColor.darkGray)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self._pan_start = None
        self.tool = None
        self.setMouseTracking(True)
        self.setMinimumSize(320, 280)
        self.setObjectName("imageCanvas")
        self.auto_fit_enabled = True
        self.fit_timer = QTimer(self)
        self.fit_timer.setSingleShot(True)
        self.fit_timer.setInterval(50)
        self.fit_timer.timeout.connect(self._fit)

    def set_image(self, raw, fit=False):
        old_size = self.image_item.pixmap().size()
        self.image_item.setPixmap(QPixmap.fromImage(to_qimage(raw)))
        h, w = raw.shape[:2]
        self.setSceneRect(QRectF(0, 0, w, h))
        if fit:
            self.fit_image()
        elif self.auto_fit_enabled and old_size != self.image_item.pixmap().size():
            self._fit()

    def clear_image(self):
        self.overlays.clear()
        self.image_item.setPixmap(QPixmap())
        self.fit_timer.stop()
        self.set_auto_fit(True)

    def fit_image(self):
        self.set_auto_fit(True)
        self._fit()
        self.fitted.emit()

    def set_auto_fit(self, enabled):
        self.auto_fit_enabled = bool(enabled)
        self.auto_fit_changed.emit(self.auto_fit_enabled)
        if enabled:
            self._fit()
        else:
            self.fit_timer.stop()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if getattr(self, 'auto_fit_enabled', False) and not self.image_item.pixmap().isNull():
            self.fit_timer.start()

    def _fit(self):
        if not self.auto_fit_enabled:
            return
        if not self.image_item.pixmap().isNull():
            # Keep a small screen-space margin for handles; allow upscaling.
            rect = self.image_item.boundingRect()
            width, height = self.viewport().width()-20, self.viewport().height()-20
            if width > 0 and height > 0:
                factor = min(width/rect.width(), height/rect.height())
                self.resetTransform()
                self.scale(factor, factor)
                self.centerOn(rect.center())

    def zoom(self, factor):
        self.set_auto_fit(False)
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
        elif event.button() == Qt.MouseButton.LeftButton and self.tool is not None and not self.image_item.pixmap().isNull():
            self.setFocus()
            self.tool.mouse_press(self.image_position(event))
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
        elif self.tool is not None and not self.image_item.pixmap().isNull():
            self.tool.mouse_move(self.image_position(event))
            event.accept()
        else:
            super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.MiddleButton:
            self._pan_start = None
            self.unsetCursor()
            event.accept()
        elif event.button() == Qt.MouseButton.LeftButton and self.tool is not None and not self.image_item.pixmap().isNull():
            self.tool.mouse_release(self.image_position(event))
            event.accept()
        else:
            super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and self.tool is not None and not self.image_item.pixmap().isNull():
            self.tool.mouse_double_click(self.image_position(event))
            event.accept()
        else:
            super().mouseDoubleClickEvent(event)

    def contextMenuEvent(self, event):
        if self.tool is None:
            return
        point = self.mapToScene(event.pos())
        position = (point.x(), point.y())
        draft = getattr(self.tool, 'draft', None)
        if draft is not None and draft.active:
            vertex = draft.hit(position, draft.handles)
            if vertex is None:
                return
            callback = lambda: draft.delete(vertex)
        else:
            editor = self.tool.editor
            record = editor.selected_record()
            index = editor.handle_at(position)
            if index is None or record is None or record.geometry_type != 'polygon' or not editor.can_edit(record):
                return
            editor.selected_vertex = index
            editor.refresh_selection()
            callback = editor.delete_vertex
        menu = QMenu(self)
        menu.addAction(tr('Delete Vertex'), callback)
        menu.exec(event.globalPos())

    def image_position(self, event):
        point = self.mapToScene(event.position().toPoint())
        size = self.image_item.pixmap().size()
        return clamp_point((point.x(), point.y()), size.width(), size.height())
