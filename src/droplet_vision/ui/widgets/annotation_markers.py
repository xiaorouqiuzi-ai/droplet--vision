"""Human-work markers with screen-space hit testing above the native slider."""
from PySide6.QtCore import QPoint, Qt, Signal, QEvent
from PySide6.QtGui import QPainter, QPolygon, QColor
from PySide6.QtWidgets import QSlider, QStyleOptionSlider, QStyle, QToolTip
from ..i18n import tr


def human_objects(document, layers, frame=None):
    if document is None:
        return []
    roles = {layer.layer_id: layer.role for layer in layers}
    return [r for r in document.active_records(frame)
            if roles.get(document.record_layers[r.annotation_id]) in ('manual', 'reviewed', 'ground_truth')
            and not (r.source == 'imported' and r.attributes.get('creation_tool') == 'cine_template_projection')
            and (r.source != 'model' or r.review_status in ('accepted', 'edited', 'ground_truth'))]


def human_state(record):
    return record is not None and (record.source == 'manual'
        or record.review_status in ('accepted', 'edited', 'ground_truth'))


def human_frames(document, layers):
    if document is None:
        return set()
    result = {r.frame_index for r in human_objects(document, layers)}
    result.update(int(frame) for frame in document.support_templates.get('support_structure', {}).get('frame_overrides', {}))
    result.update(r.frame_index for r in document.frame_state_records
                  if human_state(r) and document.active_frame_state_records.get(r.frame_index) == r.record_id)
    return result


class MarkedSlider(QSlider):
    marker_clicked = Signal(int)
    HIT_RADIUS = 7  # 15 logical pixels including the center, independent of zoom.

    def __init__(self, parent=None):
        super().__init__(Qt.Orientation.Horizontal, parent)
        self.marked_frames = set()
        self.available_frames = set()
        self.target_frames = set()
        self.marker_details = None  # Lazy callback, always resolves the current document/language.
        self._marker_press = False
        self.setMouseTracking(True)
        self.setMinimumHeight(32)

    def set_markers(self, frames):
        self.marked_frames = set(frames)
        self.update()

    def set_package_markers(self, available, targets):
        self.available_frames, self.target_frames = set(available), set(targets)
        self.update()

    def marker_positions(self, frames=None):
        return set(self.marker_columns(frames))

    def marker_columns(self, frames=None):
        option = QStyleOptionSlider()
        self.initStyleOption(option)
        style = self.style()
        groove = style.subControlRect(QStyle.ComplexControl.CC_Slider, option,
                                      QStyle.SubControl.SC_SliderGroove, self)
        handle = style.subControlRect(QStyle.ComplexControl.CC_Slider, option,
                                      QStyle.SubControl.SC_SliderHandle, self)
        span = max(0, groove.width() - handle.width())
        left = groove.left() + handle.width() // 2
        columns = {}
        for frame in sorted(self.marked_frames if frames is None else frames):
            if self.minimum() <= frame <= self.maximum():
                x = left + QStyle.sliderPositionFromValue(self.minimum(), self.maximum(), frame, span, option.upsideDown)
                columns.setdefault(x, []).append(frame)
        return columns

    def marker_at(self, pos):
        if self.height()-10 <= pos.y() <= self.height() and self.available_frames:
            columns = self.marker_columns(self.available_frames)
        elif 0 <= pos.y() <= 10:
            columns = self.marker_columns()
        else:
            return None
        candidates = [(abs(x-pos.x()), x, frames) for x,frames in columns.items()
                      if abs(x-pos.x()) <= self.HIT_RADIUS]
        if not candidates:
            return None
        _, _, frames = min(candidates, key=lambda item:(item[0], item[1]))
        return min(frames, key=lambda f:(abs(f-self.value()),f)), frames

    def marker_tooltip(self, pos):
        hit = self.marker_at(pos)
        if hit is None:
            return ''
        frame, frames = hit
        lines = [tr('Frame: {frame}').format(frame=frame)]
        if len(frames) > 1:
            title = ('Multiple available frames ({count}); nearest to current frame' if pos.y() >= self.height()-10
                     else 'Multiple annotated frames ({count}); nearest to current frame')
            lines.insert(0,tr(title).format(count=len(frames)))
        if self.marker_details is not None and pos.y() <= 10:
            lines.extend(self.marker_details(frame))
        return '\n'.join(lines)

    def event(self, event):
        if event.type() == QEvent.Type.ToolTip:
            text = self.marker_tooltip(event.pos())
            if text:
                QToolTip.showText(event.globalPos(), text, self)
            else:
                QToolTip.hideText()
                event.ignore()
            return True
        return super().event(event)

    def mousePressEvent(self, event):
        hit = self.marker_at(event.position()) if event.button() == Qt.MouseButton.LeftButton else None
        self._marker_press = hit is not None
        if hit is not None:
            self.marker_clicked.emit(hit[0])
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._marker_press:
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if self._marker_press:
            self._marker_press = False
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def paintEvent(self, event):
        super().paintEvent(event)
        painter = QPainter(self)
        color = self.palette().highlight().color()
        painter.setPen(color)
        painter.setBrush(color)
        # Above the native groove/handle, never a graphics item or input target.
        for x in self.marker_positions():
            painter.drawPolygon(QPolygon([QPoint(x-3, 1), QPoint(x+3, 1), QPoint(x, 5)]))
            painter.drawLine(x, 6, x, 10)
        painter.setPen(QColor('#91A1B2'))
        for x in self.marker_positions(self.available_frames):
            painter.drawLine(x, self.height()-5, x, self.height()-2)
        painter.setPen(QColor('#E9A23B'))
        painter.setBrush(QColor('#E9A23B'))
        for x in self.marker_positions(self.target_frames):
            y = self.height()-6
            painter.drawPolygon(QPolygon([QPoint(x-3,y+4),QPoint(x+3,y+4),QPoint(x,y)]))
