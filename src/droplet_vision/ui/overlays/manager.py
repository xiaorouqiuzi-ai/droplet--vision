"""Geometry renderer registry; independent of label names and model backends."""
from PySide6.QtCore import QPointF
from PySide6.QtGui import QPen, QColor, QPolygonF


def _point(scene, geometry, pen):
    x, y = geometry["point"]
    return scene.addEllipse(x - 2, y - 2, 4, 4, pen)


def _bbox(scene, geometry, pen):
    return scene.addRect(*geometry["bbox"], pen)  # x, y, width, height


def _polygon(scene, geometry, pen):
    return scene.addPolygon(QPolygonF([QPointF(*p) for p in geometry["points"]]), pen)


class OverlayManager:
    def __init__(self, scene):
        self.scene = scene
        self.items = []
        self.renderers = {"point": _point, "bbox": _bbox, "polygon": _polygon}

    def register(self, geometry_type, renderer):
        self.renderers[geometry_type] = renderer

    def clear(self):
        for item in self.items:
            self.scene.removeItem(item)
        self.items.clear()

    def render(self, layers, cine_id, frame_index):
        self.clear()
        for layer in layers:
            if not layer.visible:
                continue
            for record in layer.annotations:
                renderer = self.renderers.get(record.geometry_type)
                if record.cine_id != cine_id or record.frame_index != frame_index or renderer is None:
                    continue
                pen = QPen(QColor("#00d9c0"), 1)
                pen.setCosmetic(True)
                item = renderer(self.scene, record.geometry, pen)
                item.setZValue(10)
                item.setToolTip(record.label_id + " / " + layer.name)
                self.items.append(item)
