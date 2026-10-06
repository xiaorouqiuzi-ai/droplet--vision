"""Shared transient polygon editor. No AnnotationDocument writes before confirmation."""
from copy import deepcopy
from PySide6.QtCore import QPointF, Qt, QTimer
from PySide6.QtGui import QColor, QPainterPath, QPen, QBrush
from PySide6.QtWidgets import QGraphicsItem
from ..i18n import tr


class DraftPolygonEditor:
    def __init__(self, editor):
        self.editor = editor
        self.polygons = [[]]
        self.closed = False
        self.manual_edited = False
        self.selected = None
        self.drag = None
        self.pending_close = False
        self.cursor = None
        self.handles = []
        self.midpoints = []
        self.paths = []
        self.items = []
        self.history = []
        self.future = []
        self.offset = 0
        self.timer = QTimer(editor)
        self.timer.setInterval(100)
        self.timer.timeout.connect(self.animate)

    @property
    def active(self):
        return any(self.polygons)

    def snapshot(self):
        return deepcopy((self.polygons, self.closed, self.manual_edited))

    def remember(self, before):
        if before != self.snapshot():
            self.history.append(before)
            self.future.clear()

    def restore(self, state):
        self.polygons, self.closed, self.manual_edited = deepcopy(state)
        self.selected = self.drag = None
        self.pending_close = False
        self.render()

    def undo(self):
        if self.drag is not None:
            self.restore(self.drag[2])
        elif self.history:
            self.future.append(self.snapshot())
            self.restore(self.history.pop())

    def redo(self):
        if self.future:
            self.history.append(self.snapshot())
            self.restore(self.future.pop())

    def replace(self, polygons):
        self.clear()
        self.polygons = deepcopy(polygons)
        self.closed = True
        self.render()

    def near(self, position, point, radius=6):
        canvas = self.editor.canvas
        delta = canvas.mapFromScene(QPointF(*position)) - canvas.mapFromScene(QPointF(*point))
        return delta.x()**2 + delta.y()**2 <= radius**2

    def hit(self, position, handles):
        return next(((p, v) for p, v, xy, item in handles if self.near(position, xy)), None)

    def press(self, position, add=True):
        vertex = self.hit(position, self.handles)
        if vertex == (0, 0) and not self.closed and len(self.polygons[0]) >= 3:
            # A click closes; a drag still moves the first open-draft vertex.
            self.pending_close = True
            self.selected = vertex
            self.drag = (vertex, list(position), self.snapshot())
            self.render()
            return True
        midpoint = self.hit(position, self.midpoints) if vertex is None else None
        if vertex is not None or midpoint is not None:
            before = self.snapshot()
            if midpoint is not None:
                p, edge = midpoint
                points = self.polygons[p]
                a, b = points[edge], points[(edge + 1) % len(points)]
                vertex = (p, edge + 1)
                points.insert(edge + 1, [(a[0]+b[0])/2, (a[1]+b[1])/2])
                self.manual_edited = True
            self.selected = vertex
            self.drag = (vertex, list(position), before)
            self.render()
            return True
        if add and not self.closed:
            before = self.snapshot()
            self.polygons[0].append(list(position))
            self.selected = (0, len(self.polygons[0])-1)
            self.remember(before)
            self.render()
            return True
        return False

    def move(self, position):
        self.cursor = list(position)
        if self.drag is not None:
            (p, v), start, _ = self.drag
            if list(position) != start:
                self.polygons[p][v] = list(position)
                self.manual_edited = True
                self.render()
        elif not self.closed and self.active:
            self.update_paths()
            close = len(self.polygons[0]) >= 3 and self.near(position, self.polygons[0][0])
            if self.handles:
                self.handles[0][3].setBrush(QColor('#ffbb33' if close else '#ffffff'))
            if close:
                self.editor.message(tr('Click the first vertex to close the polygon.'))

    def release(self, position):
        if self.drag is not None:
            if self.pending_close and list(position) == self.drag[1]:
                self.drag = None
                self.pending_close = False
                self.close()
                return
            self.move(position)
            before = self.drag[2]
            self.drag = None
            self.pending_close = False
            self.remember(before)
            self.render()

    def close(self):
        if len(self.polygons[0]) < 3:
            self.editor.message(tr('A polygon requires at least 3 vertices.'))
            return False
        before = self.snapshot()
        self.closed = True
        self.cursor = None
        self.remember(before)
        self.render()
        self.editor.message(tr('Closed draft: adjust vertices, then Confirm.'))
        return True

    def delete(self, vertex=None):
        vertex = vertex if vertex is not None else self.selected
        if vertex is None:
            return False
        p, v = vertex
        if self.closed and len(self.polygons[p]) <= 3:
            self.editor.message(tr('A polygon requires at least 3 vertices.'))
            return False
        before = self.snapshot()
        self.polygons[p].pop(v)
        self.selected = None
        self.manual_edited = True
        self.remember(before)
        self.render()
        return True

    def remove_items(self):
        for item in self.items:
            if item.scene() is not None:
                item.scene().removeItem(item)
            if item in self.editor.preview:
                self.editor.preview.remove(item)
        self.items.clear()
        self.paths.clear()
        self.handles.clear()
        self.midpoints.clear()

    def update_paths(self):
        for points, item in zip(self.polygons, self.paths):
            path = QPainterPath()
            if points:
                path.moveTo(QPointF(*points[0]))
                for xy in points[1:]:
                    path.lineTo(QPointF(*xy))
                if self.closed:
                    path.closeSubpath()
                elif self.cursor is not None:
                    path.lineTo(QPointF(*self.cursor))
            item.setPath(path)

    def render(self):
        self.remove_items()
        scene = self.editor.canvas.scene()
        pen = QPen(QColor('#50cfff' if self.closed else '#eeeeee'), 1.5, Qt.PenStyle.DashLine)
        pen.setCosmetic(True)
        pen.setDashOffset(self.offset)
        for p, points in enumerate(self.polygons):
            item = scene.addPath(QPainterPath(), pen, QBrush(QColor(50, 180, 255, 30)) if self.closed else QBrush(Qt.BrushStyle.NoBrush))
            item.setZValue(25)
            self.paths.append(item)
            self.items.append(item)
            for v, xy in enumerate(points):
                self.handles.append((p, v, xy, self.square(xy, 8, self.selected == (p, v))))
                if self.closed:
                    other = points[(v+1) % len(points)]
                    mid = [(xy[0]+other[0])/2, (xy[1]+other[1])/2]
                    self.midpoints.append((p, v, mid, self.square(mid, 5, False, hollow=True)))
        self.update_paths()
        self.editor.preview.extend(self.items)
        if self.active:
            if not self.timer.isActive():
                self.timer.start()
        else:
            self.timer.stop()
        self.editor.tool_settings.refresh()

    def square(self, xy, size, selected, hollow=False):
        pen = QPen(QColor('#50cfff'), 1)
        pen.setCosmetic(True)
        brush = QBrush(Qt.BrushStyle.NoBrush) if hollow else QBrush(QColor('#ffbb33' if selected else '#ffffff'))
        item = self.editor.canvas.scene().addRect(-size/2, -size/2, size, size, pen, brush)
        item.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIgnoresTransformations, True)
        item.setPos(*xy)
        item.setZValue(32 if not hollow else 31)
        self.items.append(item)
        return item

    def animate(self):
        # Reuse items and geometry: only change cosmetic pen dash phase at 10 Hz.
        self.offset = (self.offset + .5) % 12
        for item in self.paths:
            pen = item.pen()
            pen.setDashOffset(self.offset)
            item.setPen(pen)

    def clear(self):
        self.timer.stop()
        self.remove_items()
        self.polygons = [[]]
        self.closed = self.manual_edited = False
        self.selected = self.drag = self.cursor = None
        self.pending_close = False
        self.history.clear()
        self.future.clear()

    def dispose(self):
        self.clear()
        self.timer.deleteLater()
