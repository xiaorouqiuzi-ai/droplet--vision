"""Annotation document/UI coordinator; pixel display and Cine I/O remain separate."""
from __future__ import annotations
from dataclasses import asdict
from pathlib import Path

from PySide6.QtCore import QObject, QPointF, Qt, QTimer
from PySide6.QtGui import QAction, QActionGroup, QColor, QKeySequence, QPainterPath, QPen, QUndoStack
from PySide6.QtWidgets import QFileDialog, QGraphicsItem, QLabel, QMessageBox, QToolBar

from ..annotations import AnnotationDocument, AnnotationRecord
from .annotation_commands import AddAnnotationCommand, EditAnnotationCommand, DeactivateAnnotationCommand
from .tools.base import ToolRegistry
from .tools.drawing import SelectTool, PointTool, BBoxTool, PolygonTool


class AnnotationEditor(QObject):
    def __init__(self, window, taxonomy_path):
        super().__init__(window)
        self.window, self.canvas = window, window.canvas
        self.document = None
        self.path = None
        self.ready = False
        self.selected_id = None
        self.preview = []
        self.handles = []
        self.taxonomy_metadata = {"reference": Path(taxonomy_path).name,
                                  "labels": [asdict(label) for label in window.annotation_panel.taxonomy.values()]}
        self.undo_stack = QUndoStack(self)
        self.registry = ToolRegistry()
        self.actions = {}
        self.toolbar = QToolBar("Annotation tools", window)
        self.toolbar.setObjectName("annotationTools")
        window.addToolBar(self.toolbar)
        self.action_group = QActionGroup(self)
        self.action_group.setExclusive(True)
        for key, title, shortcut, cls in (("select", "Select", "1", SelectTool),
                                          ("point", "Point", "2", PointTool),
                                          ("bbox", "BBox", "3", BBoxTool),
                                          ("polygon", "Polygon", "4", PolygonTool)):
            self.registry.register(key, lambda tool_class=cls: tool_class(self))
            action = QAction(title, self)
            action.setCheckable(True)
            action.setShortcut(QKeySequence(shortcut))
            action.setData(cls.geometry_type)
            action.triggered.connect(lambda checked=False, tool_id=key: self.switch_tool(tool_id))
            self.toolbar.addAction(action)
            self.action_group.addAction(action)
            self.actions[key] = action
        self.frame_count_label = QLabel("Annotated: 0 | Annotated frames: 0")
        self.toolbar.addWidget(self.frame_count_label)
        menu = window.annotation_menu
        menu.addSeparator()
        window._action(menu, "New Annotation Document", self.new_document)
        open_annotations = window._action(menu, "Open Annotations...", self.open_dialog, "Ctrl+Shift+O")
        open_annotations.setShortcuts([QKeySequence("Ctrl+Shift+O"), QKeySequence("Ctrl+Alt+O")])
        open_annotations.setToolTip("Open annotation JSON (Ctrl+Shift+O or Ctrl+Alt+O)")
        window._action(menu, "Save Annotations", self.save_dialog, "Ctrl+Shift+S")
        window._action(menu, "Save Annotations As...", lambda: self.save_dialog(save_as=True))
        undo = self.undo_stack.createUndoAction(self, "Undo")
        redo = self.undo_stack.createRedoAction(self, "Redo")
        undo.setShortcut(QKeySequence("Ctrl+Z"))
        redo.setShortcuts([QKeySequence("Ctrl+Y"), QKeySequence("Ctrl+Shift+Z")])
        menu.addAction(undo)
        menu.addAction(redo)
        window._action(menu, "Deactivate Selected", self.deactivate_selected, "Delete")
        window._action(menu, "Cancel drawing", self.cancel, "Esc")
        commit = window._action(menu, "Commit drawing", lambda: self.tool.commit(), "Return")
        commit.setShortcuts([QKeySequence("Return"), QKeySequence("Enter")])
        window._action(menu, "Remove last polygon vertex", lambda: self.tool.backspace(), "Backspace")
        window._action(menu, "Previous Annotated Frame", lambda: self.annotated_frame(-1), "Alt+Left")
        window._action(menu, "Next Annotated Frame", lambda: self.annotated_frame(1), "Alt+Right")
        self.tool = None
        self.switch_tool("select")
        window.annotation_panel.label_changed.connect(self.update_tools)
        window.annotation_panel.annotation_selected.connect(self.select)
        window.layer_panel.changed.connect(self.layer_changed)
        self.autosave_timer = QTimer(self)
        self.autosave_timer.setInterval(30000)
        self.autosave_timer.timeout.connect(self.autosave)
        self.autosave_timer.start()
        self.update_tools()

    def message(self, text):
        self.window.statusBar().showMessage(text)

    def drawing_layer(self):
        key = self.window.layer_panel.active_layer.currentData()
        return next((layer for layer in self.window.layers if layer.layer_id == key), None)

    def can_draw(self, kind):
        label = self.window.annotation_panel.selected_label()
        layer = self.drawing_layer()
        return bool(self.ready and self.document is not None and label and label.enabled
                    and kind in label.allowed_geometry_types and layer and layer.visible
                    and not layer.locked and layer.role in ("manual", "reviewed"))

    def update_tools(self):
        for action in self.actions.values():
            action.setEnabled(self.ready if action.data() is None else self.can_draw(action.data()))
        if self.tool is not None and self.tool.geometry_type and not self.can_draw(self.tool.geometry_type):
            self.switch_tool("select")

    def layer_changed(self):
        self.cancel()
        self.update_tools()
        self.select(self.selected_id)

    def switch_tool(self, key):
        if self.tool is not None:
            self.tool.deactivate()
        self.window.pause()
        self.tool = self.registry.create(key)
        self.tool.activate(self.canvas)
        self.canvas.tool = self.tool
        self.actions[key].setChecked(True)
        self.refresh_selection()

    def reset(self):
        self.cancel()
        self.ready = False
        self.document = self.path = self.selected_id = None
        self.clear_handles()
        self.window.annotation_panel.select_record(None)
        self.undo_stack.clear()
        self.update_tools()
        self.update_title()
        self.frame_count_label.setText("Annotated: 0 | Annotated frames: 0")

    def frame_will_change(self):
        cancelled = bool(self.preview)
        self.cancel()
        self.select(None)
        self.ready = False
        self.update_tools()
        return cancelled

    def frame_loaded(self):
        self.ready = True
        if self.document is None:
            self._create_document()
        self.update_tools()
        self.update_counts()

    def _create_document(self):
        metadata, record = self.window.metadata, self.window.current_record
        self.document = AnnotationDocument(record.cine_id, metadata.filename, metadata.file_size_bytes,
                                           metadata.frame_count, metadata.width, metadata.height,
                                           self.taxonomy_metadata)
        self.path = None
        self.undo_stack.clear()
        self.changed()

    def new_document(self):
        if self.ready and self.confirm_discard():
            self.cancel()
            self._create_document()

    def selected_record(self):
        if self.document is not None and self.selected_id in self.document.active_annotation_ids:
            return self.document.records.get(self.selected_id)
        return None

    def can_edit(self, record):
        if not self.ready or self.document is None or record.annotation_id not in self.document.active_annotation_ids:
            return False
        layer_id = self.document.record_layers[record.annotation_id]
        layer = next((item for item in self.window.layers if item.layer_id == layer_id), None)
        return bool(layer and layer.visible and not layer.locked and
                    record.frame_index == self.window.current_record.frame_index)

    def create_annotation(self, kind, geometry):
        if not self.can_draw(kind):
            self.message("Choose a label and an unlocked Manual/Reviewed layer allowing this geometry.")
            return False
        if kind == "bbox" and min(geometry["bbox"][2:]) < 1:
            self.message("BBox must span at least one raw image pixel in each direction (not a physical size threshold).")
            return False
        self.window.pause()
        label = self.window.annotation_panel.selected_label()
        frame = self.window.current_record
        record = AnnotationRecord(frame.cine_id, frame.frame_index, label.label_id, kind, geometry,
                                  attributes={"raw_time64": frame.timestamp_time64,
                                              "relative_timestamp_s": frame.timestamp_s,
                                              "display_mode_used": self.window.display_panel.settings.mode})
        try:
            self.document.validate_record(record)
        except ValueError as error:
            self.message(str(error))
            return False
        self.selected_id = record.annotation_id
        self.undo_stack.push(AddAnnotationCommand(self.document, record, self.drawing_layer().layer_id, self.changed))
        return True

    def edit_annotation(self, annotation_id, geometry):
        original = self.document.records.get(annotation_id)
        if not self.can_edit(original):
            self.message("This annotation layer is locked or unavailable for editing.")
            return False
        label = self.window.annotation_panel.taxonomy.get(original.label_id)
        if label is not None and original.geometry_type not in label.allowed_geometry_types:
            self.message("Geometry is not allowed by the current taxonomy label.")
            return False
        try:
            derived = self.document.derive(annotation_id, geometry)
        except ValueError as error:
            self.message(str(error))
            return False
        derived.attributes["display_mode_used"] = self.window.display_panel.settings.mode
        layer_id = "reviewed" if original.source == "model" else self.document.record_layers[annotation_id]
        target = next((layer for layer in self.window.layers if layer.layer_id == layer_id), None)
        if target is None or target.locked:
            self.message("Derivative target layer is locked.")
            return False
        self.selected_id = derived.annotation_id
        self.undo_stack.push(EditAnnotationCommand(self.document, annotation_id, derived, layer_id, self.changed))
        return True

    def deactivate_selected(self):
        record = self.selected_record()
        if record is not None and self.can_edit(record):
            self.cancel()
            self.undo_stack.push(DeactivateAnnotationCommand(self.document, record.annotation_id, self.changed))

    def changed(self):
        if self.document is not None:
            for layer in self.window.layers:
                layer.annotations = [record for record in self.document.active_records()
                                     if self.document.record_layers[record.annotation_id] == layer.layer_id]
        self.window.refresh_overlays()
        self.update_counts()
        self.update_title()

    def update_counts(self):
        if self.document is not None and self.window.current_record is not None:
            count = len(self.document.active_records(self.window.current_record.frame_index))
            self.frame_count_label.setText(f"Annotated: {count} | Annotated frames: {len(self.document.annotated_frames())}")

    def update_title(self):
        self.window.setWindowTitle("Droplet Annotation Workstation — Annotation Editor v1" +
                                   (" *" if self.document is not None and self.document.dirty else ""))

    def select(self, annotation_id):
        self.selected_id = annotation_id
        record = self.selected_record()
        if record is None or record.frame_index != self.window.current_record.frame_index:
            self.selected_id = None
        self.refresh_selection()

    def refresh_selection(self):
        self.clear_handles()
        record = self.selected_record()
        self.canvas.overlays.highlight(self.selected_id)
        self.window.annotation_panel.select_record(record)
        if record is None or not self.can_edit(record) or self.tool is None or self.tool.geometry_type is not None:
            return
        for index, point in enumerate(self.geometry_handles(record.geometry_type, record.geometry)):
            pen = QPen(QColor("#ffcc33"), 1)
            pen.setCosmetic(True)
            item = self.canvas.scene().addEllipse(-5, -5, 10, 10, pen, QColor("#ffffff"))
            item.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIgnoresTransformations, True)
            item.setPos(*point)
            item.setZValue(30)
            self.handles.append((index, point, item))

    @staticmethod
    def geometry_handles(kind, geometry):
        def corners():
            x, y, width, height = geometry["bbox"]
            return [[x, y], [x+width, y], [x+width, y+height], [x, y+height]]
        return {"point": lambda: [geometry["point"]], "polygon": lambda: geometry["points"],
                "bbox": corners}[kind]()

    def handle_at(self, position):
        for index, point, item in self.handles:
            if (QPointF(*position) - QPointF(*point)).manhattanLength() * self.canvas.transform().m11() <= 12:
                return index
        return None

    def annotation_at(self, position):
        point = QPointF(*position)
        for item in self.canvas.scene().items(point):
            if item.data(0) in self.canvas.overlays.by_id:
                return item.data(0)
        return None

    def clear_handles(self):
        for _, _, item in self.handles:
            self.canvas.scene().removeItem(item)
        self.handles.clear()

    def clear_preview(self):
        for item in self.preview:
            self.canvas.scene().removeItem(item)
        self.preview.clear()

    def preview_geometry(self, kind, geometry):
        self.clear_preview()
        pen = QPen(QColor("#ffcc33"), 2)
        pen.setCosmetic(True)
        item = self.canvas.overlays.renderers[kind](self.canvas.scene(), geometry, pen)
        item.setZValue(25)
        self.preview.append(item)

    def preview_polygon(self, points):
        self.clear_preview()
        if not points:
            return
        path = QPainterPath(QPointF(*points[0]))
        for point in points[1:]:
            path.lineTo(QPointF(*point))
        pen = QPen(QColor("#ffcc33"), 2)
        pen.setCosmetic(True)
        item = self.canvas.scene().addPath(path, pen)
        item.setZValue(25)
        self.preview.append(item)

    def cancel(self):
        if self.tool is not None:
            self.tool.cancel()
        self.clear_preview()
        self.refresh_selection()

    def annotated_frame(self, direction):
        if not self.ready or self.document is None:
            return
        current = self.window.current_record.frame_index
        candidates = [i for i in self.document.annotated_frames() if (i-current)*direction > 0]
        if candidates:
            self.window.navigate(min(candidates) if direction > 0 else max(candidates))

    def default_path(self):
        return Path("outputs/annotations") / (Path(self.document.cine_filename).stem + ".annotations.json")

    def save(self, path):
        if self.document is None:
            raise ValueError("No annotation document")
        self.document.save(path)
        self.path = Path(path)
        self.undo_stack.setClean()
        self.update_title()

    def save_dialog(self, checked=False, save_as=False):
        if self.document is None:
            return False
        path = self.path
        if path is None or save_as:
            default = path or self.default_path()
            default.parent.mkdir(parents=True, exist_ok=True)
            filename, _ = QFileDialog.getSaveFileName(self.window, "Save Annotations", str(default), "Annotation JSON (*.json)")
            if not filename:
                return False
            path = Path(filename)
        try:
            self.save(path)
            self.message("Annotations saved: " + path.name)
            return True
        except Exception as error:
            self.window._error("Annotation save failed: " + str(error))
            return False

    def confirm_discard(self):
        if self.document is None or not self.document.dirty:
            return True
        self.window.pause()
        answer = QMessageBox.warning(self.window, "Unsaved annotations",
                                     "Save annotation changes before continuing?",
                                     QMessageBox.StandardButton.Save | QMessageBox.StandardButton.Discard | QMessageBox.StandardButton.Cancel,
                                     QMessageBox.StandardButton.Cancel)
        if answer == QMessageBox.StandardButton.Save:
            return self.save_dialog()
        return answer == QMessageBox.StandardButton.Discard

    def load(self, path):
        if not self.ready:
            raise ValueError("Open a Cine and wait for a frame before loading annotations")
        document = AnnotationDocument.load(path)
        meta = self.window.metadata
        if not document.matches_cine(meta.filename, meta.file_size_bytes, meta.frame_count, meta.width, meta.height) or document.cine_id != self.window.current_record.cine_id:
            raise ValueError("Annotation document does not match current Cine.")
        known_layers = {layer.layer_id for layer in self.window.layers}
        if not set(document.record_layers.values()) <= known_layers:
            raise ValueError("Annotation document contains unavailable layers")
        if not self.confirm_discard():
            return False
        self.cancel()
        self.document, self.path = document, Path(path)
        self.selected_id = None
        self.undo_stack.clear()
        self.changed()
        return True

    def open_dialog(self):
        if not self.ready:
            return
        path, _ = QFileDialog.getOpenFileName(self.window, "Open Annotations", "outputs/annotations", "Annotation JSON (*.json)")
        if path:
            try:
                self.load(path)
            except Exception as error:
                self.window._error(str(error))

    def autosave(self):
        if self.document is None or not self.document.dirty:
            return
        # Stable document UUID prevents two Cine files with the same stem overwriting recovery data.
        path = Path("outputs/annotations/autosave") / (
            Path(self.document.cine_filename).stem + "." + self.document.document_id + ".annotations.autosave.json")
        try:
            self.document.save(path, mark_saved=False)
        except Exception as error:
            self.message("Annotation autosave failed: " + str(error))
