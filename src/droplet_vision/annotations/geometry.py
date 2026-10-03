"""Editor v1 geometry, in raw pixel-center coordinates (0..width-1, 0..height-1)."""
from __future__ import annotations
from math import isfinite
from numbers import Real
from typing import Any, Dict


def clamp_point(point, width: int, height: int):
    return [max(0.0, min(width - 1.0, float(point[0]))),
            max(0.0, min(height - 1.0, float(point[1])))]


def validate_geometry(kind: str, geometry: Dict[str, Any], width: int, height: int) -> None:
    if width < 1 or height < 1:
        raise ValueError("Image dimensions must be positive")

    def point(value):
        if not isinstance(value, (list, tuple)) or len(value) != 2:
            raise ValueError("A point requires two coordinates")
        if any(isinstance(x, bool) or not isinstance(x, Real) or not isfinite(x) for x in value):
            raise ValueError("Coordinates must be finite numbers")
        if not 0 <= value[0] <= width - 1 or not 0 <= value[1] <= height - 1:
            raise ValueError("Geometry is outside raw image bounds")

    if kind == "point":
        point(geometry.get("point"))
    elif kind == "bbox":
        box = geometry.get("bbox")
        if not isinstance(box, (list, tuple)) or len(box) != 4:
            raise ValueError("BBox requires x, y, width, height")
        if any(isinstance(x, bool) or not isinstance(x, Real) or not isfinite(x) for x in box):
            raise ValueError("BBox values must be finite numbers")
        x, y, w, h = box
        if w <= 0 or h <= 0:
            raise ValueError("BBox width and height must be positive")
        point([x, y])
        point([x + w, y + h])
    elif kind == "polygon":
        points = geometry.get("points")
        if not isinstance(points, (list, tuple)) or len(points) < 3:
            raise ValueError("Polygon requires at least three vertices")
        for vertex in points:
            point(vertex)
        if len({tuple(p) for p in points}) < 3 or points[0] == points[-1]:
            raise ValueError("Polygon needs three distinct vertices without repeated closing point")
    else:
        raise ValueError("Annotation Editor v1 supports point, bbox and polygon documents")
