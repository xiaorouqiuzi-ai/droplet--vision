"""Point, box, polygon and select tools operating exclusively in scene/raw coordinates."""
from copy import deepcopy
from .base import AnnotationTool


class EditorTool(AnnotationTool):
    geometry_type = None

    def __init__(self, editor):
        self.editor = editor

    def commit(self):
        pass

    def cancel(self):
        self.editor.clear_preview()


class PointTool(EditorTool):
    geometry_type = "point"

    def mouse_press(self, position):
        self.editor.create_annotation(self.geometry_type, {"point": list(position)})


class BBoxTool(EditorTool):
    geometry_type = "bbox"

    def __init__(self, editor):
        super().__init__(editor)
        self.start = self.end = None

    def mouse_press(self, position):
        if self.editor.can_draw(self.geometry_type):
            self.start = self.end = position

    def geometry(self):
        x, y = self.start
        xx, yy = self.end
        return {"bbox": [min(x, xx), min(y, yy), abs(xx-x), abs(yy-y)]}

    def mouse_move(self, position):
        if self.start is not None:
            self.end = position
            self.editor.preview_geometry(self.geometry_type, self.geometry())

    def mouse_release(self, position):
        if self.start is not None:
            self.end = position
            self.commit()

    def commit(self):
        if self.start is not None:
            geometry = self.geometry()
            self.cancel()
            self.editor.create_annotation(self.geometry_type, geometry)

    def cancel(self):
        self.start = self.end = None
        super().cancel()


class PolygonTool(EditorTool):
    geometry_type = "polygon"

    def __init__(self, editor):
        super().__init__(editor)
        self.points = []

    def mouse_press(self, position):
        if self.editor.can_draw(self.geometry_type):
            point = list(position)
            if not self.points or point != self.points[-1]:
                self.points.append(point)
            self.editor.preview_polygon(self.points)

    def mouse_move(self, position):
        if self.points:
            self.editor.preview_polygon(self.points + [list(position)])

    def mouse_double_click(self, position):
        self.mouse_press(position)
        self.commit()

    def commit(self):
        points = self.points[:]
        if len(points) > 1 and points[0] == points[-1]:
            points.pop()
        if len(points) < 3:
            self.editor.message("Polygon requires at least three vertices; continue or Esc to cancel.")
            return
        if self.editor.create_annotation(self.geometry_type, {"points": points}):
            self.cancel()

    def backspace(self):
        if self.points:
            self.points.pop()
            self.editor.preview_polygon(self.points)

    def cancel(self):
        self.points.clear()
        super().cancel()


class SelectTool(EditorTool):
    def __init__(self, editor):
        super().__init__(editor)
        self.handle = self.original = self.working = None

    def mouse_press(self, position):
        handle = self.editor.handle_at(position)
        if handle is None:
            self.editor.select(self.editor.annotation_at(position))
            handle = self.editor.handle_at(position)
        record = self.editor.selected_record()
        if handle is not None and record is not None and self.editor.can_edit(record):
            self.handle = handle
            self.original = record
            self.working = deepcopy(record.geometry)

    def mouse_move(self, position):
        if self.original is None:
            return
        kind = self.original.geometry_type
        editors = {"point": self._point, "polygon": self._polygon, "bbox": self._bbox}
        editors[kind](position)
        self.editor.preview_geometry(kind, self.working)

    def _point(self, position):
        self.working["point"] = list(position)

    def _polygon(self, position):
        self.working["points"][self.handle] = list(position)

    def _bbox(self, position):
        x, y, w, h = self.original.geometry["bbox"]
        opposite = [(x+w, y+h), (x, y+h), (x, y), (x+w, y)][self.handle]
        xx, yy = position
        self.working["bbox"] = [min(xx, opposite[0]), min(yy, opposite[1]),
                                abs(xx-opposite[0]), abs(yy-opposite[1])]

    def mouse_release(self, position):
        if self.original is not None:
            self.mouse_move(position)
            self.commit()

    def commit(self):
        if self.original is not None and self.working != self.original.geometry:
            self.editor.edit_annotation(self.original.annotation_id, self.working)
        self.cancel()

    def cancel(self):
        self.handle = self.original = self.working = None
        super().cancel()
