"""Geometry renderer registry; independent of label names and model backends."""
from PySide6.QtCore import QPointF
from PySide6.QtGui import QPen, QColor, QPolygonF, QFont, QBrush
from PySide6.QtWidgets import QGraphicsItem, QGraphicsEllipseItem, QGraphicsSimpleTextItem
from ...annotations.display_style import record_ordinals


def badge_position(record):
    geometry = record.geometry
    if record.geometry_type == 'point':
        return QPointF(*geometry['point'])
    if record.geometry_type == 'bbox':
        x, y, width, height = geometry['bbox']
        return QPointF(x + width/2, y + height/2)
    points = geometry['points']
    area = cx = cy = 0.0
    for (x, y), (u, v) in zip(points, list(points[1:]) + [points[0]]):
        cross = x*v-u*y
        area += cross
        cx += (x+u)*cross
        cy += (y+v)*cross
    if abs(area) > 1e-9:
        return QPointF(cx/(3*area), cy/(3*area))
    return QPointF(sum(p[0] for p in points)/len(points), sum(p[1] for p in points)/len(points))


def _point(scene, geometry, pen):
    x, y = geometry["point"]
    return scene.addEllipse(x - 2, y - 2, 4, 4, pen)


def _bbox(scene, geometry, pen):
    return scene.addRect(*geometry["bbox"], pen)  # x, y, width, height


def _polygon(scene, geometry, pen):
    fill = QColor(pen.color())
    fill.setAlpha(20)
    return scene.addPolygon(QPolygonF([QPointF(*p) for p in geometry["points"]]), pen, fill)


class OverlayManager:
    def __init__(self, scene):
        self.scene = scene
        self.items = []
        self.by_id = {}
        self.badges = {}
        self.renderers = {"point": _point, "bbox": _bbox, "polygon": _polygon}

    def register(self, geometry_type, renderer):
        self.renderers[geometry_type] = renderer

    def clear(self):
        for item in self.items:
            self.scene.removeItem(item)
        self.items.clear()
        self.by_id.clear()
        self.badges.clear()

    def render(self, layers, cine_id, frame_index, colors=None):
        self.clear()
        records = [r for layer in layers for r in layer.annotations
                   if r.cine_id == cine_id and r.frame_index == frame_index]
        ordinals = record_ordinals(records)
        for layer in layers:
            if not layer.visible:
                continue
            for record in layer.annotations:
                renderer = self.renderers.get(record.geometry_type)
                if record.cine_id != cine_id or record.frame_index != frame_index or renderer is None:
                    continue
                color = (colors or {}).get(record.annotation_id, self.scene.palette().text().color().name())
                pen = QPen(QColor(color), 1)
                pen.setCosmetic(True)
                item = renderer(self.scene, record.geometry, pen)
                item.setZValue(10)
                item.setToolTip(record.label_id + " / " + layer.name)
                item.setData(0, record.annotation_id)
                item.setData(1, color)
                self.by_id[record.annotation_id] = item
                self.items.append(item)
                if record.label_id == 'daughter_droplet':
                    number = ordinals[record.annotation_id]
                    badge = QGraphicsEllipseItem(-10, -10, 20, 20, item)
                    badge.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIgnoresTransformations)
                    badge.setPos(badge_position(record))
                    badge.setBrush(QBrush(QColor(color)))
                    badge.setPen(QPen(QColor(color).darker(145), 1))
                    badge.setZValue(20)
                    badge.setData(0, record.annotation_id)
                    badge.setData(2, number)
                    text = QGraphicsSimpleTextItem(str(number), badge)
                    font = QFont(); font.setPixelSize(12); font.setBold(True)
                    text.setFont(font)
                    text.setBrush(QBrush(QColor('white')))
                    bounds = text.boundingRect()
                    radius = max(10, bounds.width()/2+4)
                    badge.setRect(-radius, -radius, radius*2, radius*2)
                    text.setPos(-bounds.width()/2, -bounds.height()/2)
                    text.setData(0, record.annotation_id)
                    self.badges[record.annotation_id] = badge

    def highlight(self, annotation_id):
        for key, item in self.by_id.items():
            # Selection weight changes without losing the Scheme base color.
            pen = QPen(QColor(item.data(1)), 3 if key == annotation_id else 1)
            pen.setCosmetic(True)
            item.setPen(pen)
