"""Rigid raw-coordinate support-rod geometry helpers; no pixels or Qt."""
from math import isfinite
from numbers import Real


def translation(value):
    if (not isinstance(value, dict) or set(value) != {'dx', 'dy'}
            or any(isinstance(v, bool) or not isinstance(v, Real) or not isfinite(v) for v in value.values())):
        raise ValueError('Support translation requires finite dx/dy')
    return {'dx': float(value['dx']), 'dy': float(value['dy'])}


def translated(geometry, offset):
    return {'points': [[x + offset['dx'], y + offset['dy']] for x, y in geometry['points']]}


def group_bounds(records):
    points = [point for record in records for point in record.geometry['points']]
    return min(p[0] for p in points), min(p[1] for p in points), max(p[0] for p in points), max(p[1] for p in points)


def bounded_delta(records, dx, dy, width, height):
    """Clamp one shared delta, never individual vertices (preserves shape)."""
    left, top, right, bottom = group_bounds(records)
    return {'dx': max(-left, min(width-1-right, dx)),
            'dy': max(-top, min(height-1-bottom, dy))}
