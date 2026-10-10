"""Qt-free RAW uint8 selection assistance; never a physical classifier.

Pixel-cell edges are traced clockwise, then clamped to the editor's pixel-center
bounds. Corner-touching regions become separate simple polygons. Holes are
explicitly rejected at confirmation because polygon v1 cannot represent holes.
"""
from __future__ import annotations
from collections import deque
from dataclasses import dataclass
import json
from pathlib import Path
from ..resources import resource_path
import numpy as np


@dataclass(frozen=True)
class WandConfig:
    preset_id: str
    default_tolerance: int
    min_tolerance: int
    max_tolerance: int
    connectivity: int
    seed_window: int
    max_region_fraction: float
    polygon_simplification_tolerance_px: float

    def __post_init__(self):
        if not (0 <= self.min_tolerance <= self.default_tolerance <= self.max_tolerance <= 255):
            raise ValueError('Invalid tolerance range')
        if self.connectivity not in (4, 8) or self.seed_window != 3:
            raise ValueError('Unsupported connectivity or seed window')
        if not 0 < self.max_region_fraction <= 1 or not np.isfinite(self.polygon_simplification_tolerance_px) or self.polygon_simplification_tolerance_px < 0:
            raise ValueError('Invalid region limit or simplification tolerance')


def load_wand_config(path=None):
    path = Path(path) if path else resource_path('configs/annotations/magic_wand_v1.json')
    return WandConfig(**json.loads(path.read_text(encoding='utf-8')))


class RegionTooLarge(ValueError):
    pass


def supported_image(image):
    return isinstance(image, np.ndarray) and image.dtype == np.uint8 and image.ndim == 2 and image.size > 0


def grow_region(image, seed, tolerance, connectivity, config=None):
    config = config or load_wand_config()
    if not supported_image(image):
        raise ValueError('Magic Wand requires raw uint8 grayscale')
    if not config.min_tolerance <= tolerance <= config.max_tolerance or connectivity not in (4, 8):
        raise ValueError('Invalid Magic Wand settings')
    h, w = image.shape
    x, y = int(round(seed[0])), int(round(seed[1]))
    if not (0 <= x < w and 0 <= y < h):
        raise ValueError('Seed outside image')
    radius = config.seed_window // 2
    left, top = max(0, x-radius), max(0, y-radius)
    patch = image[top:min(h, y+radius+1), left:min(w, x+radius+1)]
    reference = float(np.median(patch))
    eligible = np.abs(image.astype(np.float32) - reference) <= tolerance
    # A noisy clicked pixel need not itself pass the median rule. Choose the
    # nearest eligible pixel in the same seed window, with deterministic ties.
    starts = [(xx, yy) for yy in range(top, top+patch.shape[0])
              for xx in range(left, left+patch.shape[1]) if eligible[yy, xx]]
    mask = np.zeros((h, w), dtype=bool)
    if not starts:
        return mask, reference
    sx, sy = min(starts, key=lambda p: ((p[0]-x)**2 + (p[1]-y)**2, p[1], p[0]))
    offsets = ((-1, 0), (1, 0), (0, -1), (0, 1))
    if connectivity == 8:
        offsets += ((-1, -1), (-1, 1), (1, -1), (1, 1))
    pending = deque([(sx, sy)])
    mask[sy, sx] = True
    count = 1
    limit = image.size * config.max_region_fraction
    while pending:
        if count > limit:
            raise RegionTooLarge('Selected region is too large; lower tolerance or choose another seed.')
        xx, yy = pending.popleft()
        for dx, dy in offsets:
            nx, ny = xx+dx, yy+dy
            if 0 <= nx < w and 0 <= ny < h and eligible[ny, nx] and not mask[ny, nx]:
                mask[ny, nx] = True
                pending.append((nx, ny))
                count += 1
    return mask, reference


def combine_selection(previous, region, mode, max_fraction):
    operations = {'replace': lambda: region.copy(), 'add': lambda: previous | region,
                  'subtract': lambda: previous & ~region}
    if mode not in operations or previous.shape != region.shape:
        raise ValueError('Invalid selection operation')
    result = operations[mode]()
    if np.count_nonzero(result) > result.size * max_fraction:
        raise RegionTooLarge('Selected region is too large; lower tolerance or choose another seed.')
    return result


def _rdp(points, epsilon):
    # Iterative RDP avoids recursion limits for noisy contours.
    points = np.asarray(points, dtype=float)
    keep = {0, len(points)-1}
    pending = [(0, len(points)-1)]
    while pending:
        start, end = pending.pop()
        if end-start <= 1:
            continue
        vector = points[end]-points[start]
        length = float(vector @ vector)
        section = points[start+1:end]
        fractions = np.clip((section-points[start]) @ vector / length, 0, 1) if length else np.zeros(len(section))
        distance = np.linalg.norm(section-(points[start]+fractions[:, None]*vector), axis=1)
        offset = int(np.argmax(distance))
        if distance[offset] > epsilon:
            middle = start+1+offset
            keep.add(middle)
            pending.extend([(start, middle), (middle, end)])
    return points[sorted(keep)].tolist()


def _simple(points):
    def cross(a, b, c):
        return (b[0]-a[0])*(c[1]-a[1])-(b[1]-a[1])*(c[0]-a[0])
    def intersects(a, b, c, d):
        if max(a[0],b[0]) < min(c[0],d[0]) or max(c[0],d[0]) < min(a[0],b[0]) or max(a[1],b[1]) < min(c[1],d[1]) or max(c[1],d[1]) < min(a[1],b[1]):
            return False
        return cross(a,b,c)*cross(a,b,d) <= 0 and cross(c,d,a)*cross(c,d,b) <= 0
    n = len(points)
    return all(not intersects(points[i],points[(i+1)%n],points[j],points[(j+1)%n])
               for i in range(n) for j in range(i+2,n) if not (i==0 and j==n-1))


def mask_to_polygons(mask, epsilon=1.0):
    """Ordered cell-edge contours; refuse holes/degeneracy, never silently fill them."""
    if mask.ndim != 2 or mask.dtype != bool or not np.isfinite(epsilon) or epsilon < 0:
        raise ValueError('Expected a binary selection and nonnegative tolerance')
    h, w = mask.shape
    edges = set()
    for y, x in zip(*np.nonzero(mask)):
        for a, b, outside in (((x,y),(x+1,y),y==0 or not mask[y-1,x]),
                              ((x+1,y),(x+1,y+1),x==w-1 or not mask[y,x+1]),
                              ((x+1,y+1),(x,y+1),y==h-1 or not mask[y+1,x]),
                              ((x,y+1),(x,y),x==0 or not mask[y,x-1])):
            if outside:
                edges.add((a,b))
    outgoing = {}
    for a,b in edges:
        outgoing.setdefault(a, set()).add(b)
    contours = []
    directions = {(1,0):0,(0,1):1,(-1,0):2,(0,-1):3}
    while edges:
        start, following = min(edges)
        current, points = start, []
        while True:
            points.append(current)
            edges.remove((current, following))
            outgoing[current].remove(following)
            previous, current = current, following
            if current == start:
                break
            direction = directions[(current[0]-previous[0],current[1]-previous[1])]
            candidates = outgoing.get(current, set())
            if not candidates:
                raise ValueError('Open selection boundary')
            # Right, straight, left, reverse: separate diagonal contacts.
            following = min(candidates, key=lambda p: {1:0,0:1,3:2,2:3}[(directions[(p[0]-current[0],p[1]-current[1])]-direction)%4])
        area = sum(a[0]*b[1]-b[0]*a[1] for a,b in zip(points,points[1:]+points[:1]))/2
        if area <= 0:
            raise ValueError('Selection contains holes; polygon v1 cannot represent holes. Adjust the selection.')
        # Remove collinear vertices before simplification and map cell edges to
        # raw pixel centers, without changing the image/annotation coordinate grid.
        corners = [p for i,p in enumerate(points) if
                   (p[0]-points[i-1][0],p[1]-points[i-1][1]) !=
                   (points[(i+1)%len(points)][0]-p[0],points[(i+1)%len(points)][1]-p[1])]
        original = [[float(np.clip(x-.5,0,w-1)),float(np.clip(y-.5,0,h-1))] for x,y in corners]
        original = [p for i,p in enumerate(original) if p != original[i-1]]
        if len(original)<3 or not _simple(original):
            raise ValueError('Selection cannot form a simple polygon inside image bounds')
        split = int(np.argmax(np.linalg.norm(np.asarray(original)-original[0],axis=1)))
        simplified = _rdp(original[:split+1],epsilon)[:-1] + _rdp(original[split:]+original[:1],epsilon)[:-1]
        if len(simplified)<3 or not _simple(simplified):
            simplified = original
        contours.append(simplified)
    return contours
