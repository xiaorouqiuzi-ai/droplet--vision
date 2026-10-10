"""Point, box, polygon and select tools operating exclusively in scene/raw coordinates."""
from ..i18n import tr
from copy import deepcopy
from .base import AnnotationTool
from ...annotations.geometry import nearest_polygon_segment


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
        from .draft_polygon import DraftPolygonEditor
        self.draft = DraftPolygonEditor(editor)

    @property
    def points(self):
        return self.draft.polygons[0]

    def mouse_press(self, position):
        if self.editor.can_draw(self.geometry_type):
            self.draft.press(position)

    def mouse_move(self, position):
        self.draft.move(position)

    def mouse_release(self, position):
        self.draft.release(position)

    def mouse_double_click(self, position):
        # Closing is never persistence, including the legacy double-click gesture.
        if not self.draft.closed:
            if not self.points or list(position) != self.points[-1]:
                self.draft.press(position)
            self.draft.close()

    def commit(self):
        if not self.draft.closed:
            self.draft.close()
            return False
        if self.editor.create_annotation('polygon', {'points': deepcopy(self.points)}):
            self.cancel()
            self.editor.switch_tool('select')
            return True
        return False

    def backspace(self):
        if self.points:
            self.draft.delete((0, len(self.points)-1))

    def cancel(self):
        self.draft.clear()
        super().cancel()

    def deactivate(self):
        self.cancel()
        self.draft.dispose()


class SelectTool(EditorTool):
    def __init__(self, editor):
        super().__init__(editor)
        self.handle = self.original = self.working = None
        self.midpoint_press = None

    def mouse_press(self, position):
        if self.editor.support_move.press(position):
            return
        handle = self.editor.handle_at(position)
        midpoint = self.editor.midpoint_at(position) if handle is None else None
        record = self.editor.selected_record()
        if midpoint is not None and record is not None and self.editor.can_edit(record):
            self.original = record
            self.midpoint_press = list(position)
            self.working = deepcopy(record.geometry)
            points = self.working['points']
            other = points[(midpoint + 1) % len(points)]
            point = [(points[midpoint][0] + other[0]) / 2, (points[midpoint][1] + other[1]) / 2]
            self.handle = midpoint + 1
            points.insert(self.handle, point)
            self.editor.selected_vertex = self.handle
            self.editor.preview_geometry('polygon', self.working)
            return
        if handle is None:
            selected = self.editor.selected_record()
            near_edge = (selected is not None and selected.geometry_type == 'polygon' and
                         nearest_polygon_segment(selected.geometry['points'], position)[2]**.5 *
                         abs(self.editor.canvas.transform().m11()) <= 12)
            if not near_edge:
                self.editor.select(self.editor.annotation_at(position))
            handle = self.editor.handle_at(position)
        record = self.editor.selected_record()
        self.editor.selected_vertex = handle if record is not None and record.geometry_type == 'polygon' else None
        self.editor.refresh_selection()
        if handle is not None and record is not None and self.editor.can_edit(record):
            self.handle = handle
            self.original = record
            self.working = deepcopy(record.geometry)

    def mouse_move(self, position):
        if self.editor.support_move.drag is not None:
            self.editor.support_move.move(position)
            return
        if self.original is None:
            self.editor.hover_midpoint(position)
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
        if self.editor.support_move.drag is not None:
            self.editor.support_move.release(position)
            return
        if self.original is not None:
            if self.midpoint_press is None or list(position) != self.midpoint_press:
                self.mouse_move(position)
            self.commit()

    def commit(self):
        if self.original is not None and self.working != self.original.geometry:
            vertex = self.editor.selected_vertex
            self.editor.edit_annotation(self.original.annotation_id, self.working)
            self.editor.selected_vertex = vertex
            self.editor.refresh_selection()
        self.cancel()

    def mouse_double_click(self, position):
        self.cancel()
        self.editor.insert_vertex(position)

    def cancel(self):
        self.editor.support_move.cancel()
        self.handle = self.original = self.working = None
        self.midpoint_press = None
        super().cancel()
