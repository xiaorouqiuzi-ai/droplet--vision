"""Annotation document/UI coordinator; pixel display and Cine I/O remain separate."""
from __future__ import annotations
from .i18n import tr, current_language
from copy import deepcopy
from dataclasses import asdict
from pathlib import Path
from ..resources import output_path

from PySide6.QtCore import QObject, QPointF, Qt, QTimer, Signal
from PySide6.QtGui import QAction, QActionGroup, QColor, QKeySequence, QPainterPath, QPen, QUndoStack
from PySide6.QtWidgets import QFileDialog, QGraphicsItem, QLabel, QMessageBox, QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QGroupBox, QToolButton

from ..annotations import AnnotationDocument, AnnotationRecord
from ..annotations.geometry import nearest_polygon_segment
from .annotation_commands import AddAnnotationCommand, EditAnnotationCommand, DeactivateAnnotationCommand
from .tools.base import ToolRegistry
from .tools.drawing import SelectTool, PointTool, BBoxTool, PolygonTool
from .tools.magic_wand import MagicWandTool
from .panels.magic_wand_panel import MagicWandPanel
from .panels.tool_settings_panel import ToolSettingsPanel
from ..annotations.magic_wand import supported_image


class AnnotationEditor(QObject):
    saved = Signal(object)

    def __init__(self, window, taxonomy_path):
        super().__init__(window)
        self.window, self.canvas = window, window.canvas
        self.document = None
        window.timeline.slider.marker_details = self.marker_details
        self.path = None
        self.ready = False
        self.selected_id = None
        self.selected_vertex = None
        self.preview = []
        self.handles = []
        self.midpoints = []
        self.taxonomy_metadata = {"reference": Path(taxonomy_path).name,
                                  "labels": [asdict(label) for label in window.annotation_panel.taxonomy.values()]}
        self.undo_stack = QUndoStack(self)
        from .support_rod_move import SupportRodMove
        self.support_move = SupportRodMove(self)
        self.registry = ToolRegistry()
        self.wand_panel = MagicWandPanel()
        self.wand_panel.changed.connect(lambda: self.tool.recalculate() if isinstance(self.tool, MagicWandTool) else None)
        self.wand_panel.mode.currentIndexChanged.connect(lambda: self.tool.mode_changed() if isinstance(self.tool, MagicWandTool) else None)
        self.wand_panel.confirm_requested.connect(lambda: self.tool.commit() if isinstance(self.tool, MagicWandTool) else None)
        self.wand_panel.cancel_requested.connect(self.cancel)
        self.actions = {}
        self.last_tools = {}
        self.tool_key = 'select'
        self.tool_group = QGroupBox(tr('Annotation tools'))
        self.tool_buttons = {}
        tool_layout = QHBoxLayout(self.tool_group)
        tool_layout.setSpacing(2)
        tool_layout.setContentsMargins(4,4,4,4)
        window.annotation_panel.tool_host.layout().addWidget(self.tool_group)
        self.action_group = QActionGroup(self)
        self.action_group.setExclusive(True)
        for key, title, shortcut, cls in (("select", tr("Select"), "1", SelectTool),
                                          ("point", tr("Point"), "2", PointTool),

                                          ("polygon", tr("Polygon"), "4", PolygonTool),
                                          ("magic_wand", tr("Wand"), "5", MagicWandTool)):
            self.registry.register(key, lambda tool_class=cls: tool_class(self))
            action = QAction(title, self)
            action.setCheckable(True)
            action.setShortcut(QKeySequence(shortcut))
            action.setData(cls.geometry_type)
            action.triggered.connect(lambda checked=False, tool_id=key: self.switch_tool(tool_id))
            window.addAction(action)
            button = QToolButton()
            button.setDefaultAction(action)
            button.setText(tr('Wand') if key == 'magic_wand' else title)
            button.setToolTip(title)
            button.setMinimumHeight(30)
            button.setStyleSheet('QToolButton:checked { border: 2px solid #3a8dde; background: #244b70; color: white; font-weight: bold; }')
            order = ('select', 'polygon', 'magic_wand', 'point').index(key)
            tool_layout.insertWidget(min(order, tool_layout.count()), button)
            self.tool_buttons[key] = button
            self.action_group.addAction(action)
            self.actions[key] = action
        self.frame_count_label = QLabel(tr("Annotated: 0 | Annotated frames: 0"))
        window.annotation_panel.tool_host.layout().addWidget(self.frame_count_label)
        settings_group = QGroupBox(tr('Tool settings'))
        self.tool_settings = ToolSettingsPanel(self)
        QVBoxLayout(settings_group).addWidget(self.tool_settings)
        window.annotation_panel.tool_host.layout().addWidget(settings_group)
        menu = window.annotation_menu

        menu.addSeparator()
        window._action(menu, tr("New Annotation Document"), self.new_document)
        open_annotations = window._action(menu, tr("Open Annotations..."), self.open_dialog, "Ctrl+Shift+O")
        open_annotations.setShortcuts([QKeySequence("Ctrl+Shift+O"), QKeySequence("Ctrl+Alt+O")])
        open_annotations.setToolTip(tr("Open annotation JSON (Ctrl+Shift+O or Ctrl+Alt+O)"))
        window._action(menu, tr("Save Annotations"), self.save_dialog, "Ctrl+Shift+S")
        window._action(menu, tr("Save Annotations As..."), lambda: self.save_dialog(save_as=True))
        undo = QAction(tr("Undo"), self)
        redo = QAction(tr("Redo"), self)
        undo.triggered.connect(self.undo)
        redo.triggered.connect(self.redo)
        undo.setShortcut(QKeySequence("Ctrl+Z"))
        redo.setShortcuts([QKeySequence("Ctrl+Y"), QKeySequence("Ctrl+Shift+Z")])
        menu.addAction(undo)
        menu.addAction(redo)
        window._action(menu, tr("Deactivate Selected"), self.deactivate_selected, "Delete")
        window._action(menu, tr("Cancel drawing"), self.cancel, "Esc")
        commit = window._action(menu, tr("Commit drawing"), lambda: self.tool.commit(), "Return")
        commit.setShortcuts([QKeySequence("Return"), QKeySequence("Enter")])
        window._action(menu, tr("Remove last polygon vertex"), lambda: self.tool.backspace(), "Backspace")
        window._action(menu, tr("Previous Annotated Frame"), lambda: self.annotated_frame(-1), "Alt+Left")
        window._action(menu, tr("Next Annotated Frame"), lambda: self.annotated_frame(1), "Alt+Right")
        self.tool = None
        self.switch_tool("select")
        window.annotation_panel.label_changed.connect(self.label_changed)
        window.annotation_panel.annotation_selected.connect(self.select_from_list)
        window.annotation_panel.visibility_changed.connect(self.set_record_visible)
        window.annotation_panel.delete_requested.connect(self.delete_record)
        window.annotation_panel.can_delete = self.can_delete
        window.layer_panel.changed.connect(self.layer_changed)
        self.autosave_timer = QTimer(self)
        self.autosave_timer.setInterval(30000)
        self.autosave_timer.timeout.connect(self.autosave)
        self.autosave_timer.start()
        from .panels.workflow_panel import WorkflowPanel
        self.workflow = WorkflowPanel(self)
        self.update_tools()

    def message(self, text):
        self.window.statusBar().showMessage(tr(text))

    def drawing_layer(self):
        key = self.window.layer_panel.active_layer.currentData()
        return next((layer for layer in self.window.layers if layer.layer_id == key), None)

    def can_draw(self, kind):
        label = self.window.annotation_panel.selected_label()
        layer = self.drawing_layer()
        return bool(self.ready and self.document is not None and label and label.enabled
                    and kind in label.allowed_geometry_types and layer
                    and not layer.locked and layer.role in ("manual", "reviewed"))

    def update_tools(self):
        for action in self.actions.values():
            action.setEnabled(self.ready if action.data() is None else self.can_draw(action.data()))
        self.actions['magic_wand'].setEnabled(self.can_draw('polygon') and supported_image(self.window.raw_image))
        self.actions['magic_wand'].setToolTip(tr('Magic Wand uses raw uint8 grayscale pixels only.'))
        if self.tool is not None and self.tool.geometry_type and not self.can_draw(self.tool.geometry_type):
            self.switch_tool("select")

    def label_changed(self):
        if hasattr(self, "workflow"):
            self.workflow.instance_name.clear()
            self.workflow.support_template.refresh()
        self.cancel()
        self.update_tools()
        label = self.window.annotation_panel.selected_label()
        if label is None:
            return
        candidates = [self.last_tools.get(label.label_id), 'polygon', 'magic_wand', 'point']
        key = next((key for key in candidates if key in self.actions and self.actions[key].isEnabled()), None)
        if key is not None:
            self.switch_tool(key)
        else:
            self.message(tr('No compatible drawing tool is available for this label and layer.'))

    def layer_changed(self):
        self.cancel()
        self.update_tools()
        self.select(self.selected_id)
        self.workflow.support_template.refresh()

    def switch_tool(self, key):
        if self.tool is not None:
            self.tool.deactivate()
        self.window.pause()
        self.tool_key = key
        self.tool = self.registry.create(key)
        self.tool.activate(self.canvas)
        self.canvas.tool = self.tool
        self.actions[key].setChecked(True)
        self.tool_settings.show_tool(key)
        label = self.window.annotation_panel.selected_label()
        if label is not None and self.tool.geometry_type is not None and self.can_draw(self.tool.geometry_type):
            self.last_tools[label.label_id] = key
        self.refresh_selection()
        if label is not None:
            self.message(tr('Current label: {label} · Tool: {tool}. {hint}').format(
                label=self.window.annotation_panel.label_name(label), tool=self.actions[key].text(), hint=tr(self.tool_settings.HINTS[key])))

    def reset(self):
        self.cancel()
        self.ready = False
        self.support_move.clear_handle()
        self.document = self.path = self.selected_id = None
        if hasattr(self, "workflow"):
            self.workflow.notes_pending = False
            self.workflow.refresh()
        self.selected_vertex = None
        self.clear_handles()
        self.window.annotation_panel.select_record(None)
        self.undo_stack.clear()
        self.window.timeline.slider.set_markers(set())
        self.update_tools()
        self.update_title()
        self.frame_count_label.setText(tr("Annotated: 0 | Annotated frames: 0"))

    def frame_will_change(self):
        self.workflow.flush_notes()
        cancelled = bool(self.preview)
        self.cancel()
        self.select(None)
        self.ready = False
        self.support_move.clear_handle()
        self.update_tools()
        self.workflow.refresh()
        return cancelled

    def frame_loaded(self):
        self.ready = True
        new_document = self.document is None
        if new_document:
            self._create_document()
        self.update_tools()
        self.update_counts()
        self.workflow.refresh()
        if new_document and self.window.annotation_panel.selected_label() is not None:
            self.label_changed()

    def _create_document(self):
        metadata, record = self.window.metadata, self.window.current_record
        self.document = AnnotationDocument(record.cine_id, metadata.filename, metadata.file_size_bytes,
                                           metadata.frame_count, metadata.width, metadata.height,
                                           self.taxonomy_metadata)
        self.document.scheme = deepcopy(self.workflow.scheme)
        self.path = None
        self.undo_stack.clear()
        self.changed()

    def new_document(self):
        if getattr(self.window, 'review_manager', None) and self.window.review_manager.active:
            self.message(tr('Package snapshots cannot be replaced with a new annotation document.'))
            return
        if self.ready and self.confirm_discard():
            self.cancel()
            self._create_document()

    def selected_record(self):
        if self.document is not None and self.selected_id in self.document.active_annotation_ids:
            return self.document.records.get(self.selected_id)
        return self.projections().get(self.selected_id)

    def projections(self):
        if self.document is None or self.window.current_record is None:
            return {}
        return {r.annotation_id:r for r in self.document.support_projections(self.window.current_record.frame_index)}

    def hidden_ids(self):
        session = self.window.session
        values = session.ui_state.get('hidden_annotation_ids', []) if session else []
        return {v for v in values if isinstance(v, str)} if isinstance(values, list) else set()

    def set_record_visible(self, annotation_id, visible):
        if self.window.session is None:
            return
        hidden = self.hidden_ids()
        hidden.discard(annotation_id) if visible else hidden.add(annotation_id)
        self.window.session.ui_state['hidden_annotation_ids'] = sorted(hidden)
        self.window.refresh_overlays()

    def can_delete(self, annotation_id):
        if self.document is None or annotation_id not in self.document.active_annotation_ids:
            return False
        record = self.document.records.get(annotation_id)
        return record.source != 'model' and self.can_edit(record)

    def delete_record(self, annotation_id):
        if not self.can_delete(annotation_id):
            return
        self.window.pause()
        if getattr(self.window, 'review_manager', None) and self.window.review_manager.active:
            self.select(annotation_id)
            self.window.review_manager.decide('object', 'rejected')
            return
        self.cancel()
        self.undo_stack.push(DeactivateAnnotationCommand(self.document, annotation_id, self.changed))
        return None

    def can_edit(self, record):
        if record.annotation_id in self.projections():
            layer = next((layer for layer in self.window.layers if layer.layer_id == 'manual'), None)
            return bool(self.ready and layer and layer.visible and not layer.locked)
        if not self.ready or self.document is None or record.annotation_id not in self.document.active_annotation_ids:
            return False
        layer_id = self.document.record_layers[record.annotation_id]
        layer = next((item for item in self.window.layers if item.layer_id == layer_id), None)
        if getattr(self.window, 'review_manager', None) and self.window.review_manager.active:
            return bool(layer and layer.visible and record.source != 'model' and record.frame_index == self.window.current_record.frame_index)
        return bool(layer and layer.visible and not layer.locked and
                    record.frame_index == self.window.current_record.frame_index)

    def create_annotation(self, kind, geometry, attributes=None):
        if not self.can_draw(kind):
            self.message(tr("Choose a label and an unlocked Manual/Reviewed layer allowing this geometry."))
            return False
        if kind == "bbox" and min(geometry["bbox"][2:]) < 1:
            self.message(tr("BBox must span at least one raw image pixel in each direction (not a physical size threshold)."))
            return False
        self.window.pause()
        label = self.window.annotation_panel.selected_label()
        frame = self.window.current_record
        record = AnnotationRecord(frame.cine_id, frame.frame_index, label.label_id, kind, geometry,
                                  attributes={"raw_time64": frame.timestamp_time64,
                                              "relative_timestamp_s": frame.timestamp_s,
                                              "display_mode_used": self.window.display_panel.settings.mode})
        record.attributes.update(attributes or {})
        record.attributes["instance_name"] = self.workflow.instance_name.text().strip()
        if hasattr(self.window, 'review_manager'):
            self.window.review_manager.prepare_record(record)
        try:
            self.document.validate_record(record)
        except ValueError as error:
            self.message(str(error))
            return False
        self.selected_id = record.annotation_id
        self.selected_vertex = None
        self.undo_stack.push(AddAnnotationCommand(self.document, record, self.drawing_layer().layer_id, self.changed))
        return True

    def create_polygon_batch(self, polygons, attributes):
        if not polygons or not self.can_draw('polygon'):
            return False
        # Validate the whole batch before changing history or starting a macro.
        from ..annotations.geometry import validate_geometry
        try:
            for points in polygons:
                validate_geometry('polygon', {'points': points}, self.window.metadata.width, self.window.metadata.height)
        except ValueError as error:
            self.message(str(error))
            return False
        self.undo_stack.beginMacro(tr('Magic Wand polygons'))
        try:
            for points in polygons:
                self.create_annotation('polygon', {'points':points}, attributes)
        finally:
            self.undo_stack.endMacro()
        return True

    def edit_annotation(self, annotation_id, geometry, attributes=None):
        frame = self.window.current_record
        if (self.document is not None and frame is not None
                and any(self.document.support_translation(frame.frame_index).values())
                and any(r.annotation_id == annotation_id for r in self.document.support_group(frame.frame_index))):
            return self.support_move.materialize_edit(annotation_id, geometry, attributes)
        projection = self.projections().get(annotation_id)
        if projection is not None:
            if not self.can_edit(projection):
                return False
            frame = self.window.current_record
            values = deepcopy(projection.attributes)
            values.update(attributes or {})
            values.update(creation_tool=self.document.support_scope.kind + '_support_template_override', raw_time64=frame.timestamp_time64,
                          relative_timestamp_s=frame.timestamp_s, display_mode_used=self.window.display_panel.settings.mode)
            record = AnnotationRecord(frame.cine_id, frame.frame_index, 'support_structure', 'polygon',
                                      deepcopy(geometry), attributes=values)
            try:
                self.document.validate_record(record)
            except ValueError as error:
                self.message(str(error))
                return False
            self.window.review_manager.prepare_record(record)
            self.selected_id = record.annotation_id
            self.undo_stack.push(AddAnnotationCommand(self.document, record, 'manual', self.changed))
            return True
        original = self.document.records.get(annotation_id)
        if not self.can_edit(original):
            self.message(tr("This annotation layer is locked or unavailable for editing."))
            return False
        label = self.window.annotation_panel.taxonomy.get(original.label_id)
        if label is not None and original.geometry_type not in label.allowed_geometry_types:
            self.message(tr("Geometry is not allowed by the current taxonomy label."))
            return False
        try:
            derived = self.document.derive(annotation_id, geometry)
        except ValueError as error:
            self.message(str(error))
            return False
        derived.attributes.update(attributes or {})
        derived.attributes["display_mode_used"] = self.window.display_panel.settings.mode
        if hasattr(self.window, 'review_manager'):
            self.window.review_manager.prepare_record(derived)
        layer_id = "reviewed" if original.source == "model" else self.document.record_layers[annotation_id]
        if getattr(self.window, 'review_manager', None) and self.window.review_manager.active:
            layer_id = 'reviewed'
        target = next((layer for layer in self.window.layers if layer.layer_id == layer_id), None)
        if target is None or target.locked:
            self.message(tr("Derivative target layer is locked."))
            return False
        self.selected_id = derived.annotation_id
        self.undo_stack.push(EditAnnotationCommand(self.document, annotation_id, derived, layer_id, self.changed))
        return True

    def deactivate_selected(self):
        draft = getattr(self.tool, "draft", None)
        if draft is not None and draft.active:
            draft.delete()
            return
        if self.selected_vertex is not None:
            self.delete_vertex()
            return
        record = self.selected_record()
        if record is not None and record.annotation_id in self.projections():
            self.set_record_visible(record.annotation_id, False)
            return
        if record is not None and self.can_delete(record.annotation_id):
            if getattr(self.window, 'review_manager', None) and self.window.review_manager.active:
                self.window.review_manager.decide('object', 'rejected')
                return
            self.cancel()
            self.undo_stack.push(DeactivateAnnotationCommand(self.document, record.annotation_id, self.changed))

    def rename_selected(self, name):
        record = self.selected_record()
        if record is None or name.strip() == record.attributes.get('instance_name', ''):
            return False
        return self.edit_annotation(record.annotation_id, record.geometry, {'instance_name': name.strip()})

    def changed(self):
        review = getattr(self.window, 'review_manager', None)
        if review is not None:
            review.document_changed()
        if self.document is not None:
            for layer in self.window.layers:
                layer.annotations = [record for record in self.document.active_records()
                                     if self.document.record_layers[record.annotation_id] == layer.layer_id]
        self.window.refresh_overlays()
        self.update_counts()
        self.update_title()
        if hasattr(self, "workflow"):
            self.workflow.refresh()

    def update_counts(self):
        from .widgets.annotation_markers import human_frames
        self.window.timeline.slider.set_markers(human_frames(self.document, self.window.layers))
        if self.document is not None and self.window.current_record is not None:
            count = len(self.document.active_records(self.window.current_record.frame_index))
            self.frame_count_label.setText(tr(f"Annotated: {count} | Annotated frames: {len(human_frames(self.document, self.window.layers))}"))

    def marker_details(self, frame):
        from .widgets.annotation_markers import human_objects, human_state
        if self.document is None:
            return []
        lines = [tr('Objects: {count}').format(count=len(human_objects(self.document,self.window.layers,frame)))]
        offset = self.document.support_translation(frame)
        if offset['dx'] or offset['dy']:
            lines.append(tr('Frame offset: X: {dx:+.3f} px | Y: {dy:+.3f} px').format(**offset))
        state = self.document.frame_state(frame)
        if human_state(state):
            rows = {r['state_id']:r for r in self.workflow.scheme['frame_states']['states']}
            names = [self.workflow.state_name(rows[key]) if key in rows else key for key in state.state_ids]
            if names:
                lines.append(tr('States: {states}').format(states=', '.join(names)))
        return lines

    def update_title(self):
        self.window.annotation_data_panel.update_document(
            self.document, self.path, self.default_path() if self.document is not None else None,
            hasattr(self, 'workflow') and self.workflow.notes_pending)
        self.window.setWindowTitle(tr("Droplet Annotation Workstation") +
                                   (" *" if self.document is not None and (self.document.dirty or
                                    (hasattr(self, "workflow") and self.workflow.notes_pending)) else ""))
        review = getattr(self.window, 'review_manager', None)
        if review is not None and review.active:
            review.refresh_save_button()
            self.window.annotation_data_panel.update_document(
                None, review.package.path, None, review.package.dirty or self.workflow.notes_pending)
            self.window.annotation_data_panel.status.setText(tr('Unsaved changes' if review.package.dirty
                                                               or self.workflow.notes_pending else 'Saved'))
            self.window.annotation_data_panel.copy_button.setToolTip(tr('Copy Path'))
            purpose = review.package.manifest.get('package_purpose', 'review')
            subtitle = tr({'annotation': 'New annotation task', 'review': 'Review task', 'general': 'General'}[purpose])
            self.window.setWindowTitle(tr('Droplet Annotation Workstation') + ' — [' + tr('Annotation Package Mode') + ' · ' + subtitle + ']'
                                       + (' *' if review.package.dirty or self.workflow.notes_pending else ''))

    def select(self, annotation_id):
        self.selected_vertex = None
        self.selected_id = annotation_id
        record = self.selected_record()
        if record is None or record.frame_index != self.window.current_record.frame_index:
            self.selected_id = None
        self.refresh_selection()

    def select_from_list(self, annotation_id):
        if annotation_id is not None and self.tool_key != 'select':
            self.switch_tool('select')
        self.select(annotation_id)

    def refresh_selection(self):
        self.clear_handles()
        # A source-frame translation replaces its raw row with a transient
        # projection. Keep selection/vertices attached to what is rendered.
        if self.document is not None and self.window.current_record is not None and self.selected_id:
            group = self.document.support_group(self.window.current_record.frame_index)
            if self.selected_id not in {r.annotation_id for r in group}:
                source_id = (self.selected_id.split(':', 1)[1]
                             if self.selected_id.startswith(('cine-template:', 'package-template:')) else
                             self.document.support_source_id(self.document.records.get(self.selected_id))
                             if self.selected_id in self.document.record_layers else None)
                replacement = next((r for r in group if self.document.support_source_id(r) == source_id), None) if source_id else None
                if replacement is not None:
                    self.selected_id = replacement.annotation_id
        record = self.selected_record()
        if record is None:
            self.selected_vertex = None
        self.canvas.overlays.highlight(self.selected_id)
        self.window.annotation_panel.select_record(record)
        if hasattr(self, 'workflow') and record is not None:
            self.workflow.instance_name.setText(record.attributes.get('instance_name', ''))
        self.tool_settings.refresh()
        self.support_move.refresh()
        if (self.support_move.drag is not None or record is None or record.annotation_id in self.hidden_ids() or not self.can_edit(record)
                or self.tool is None or self.tool.geometry_type is not None):
            return
        for index, point in enumerate(self.geometry_handles(record.geometry_type, record.geometry)):
            pen = QPen(QColor("#ffcc33"), 1)
            pen.setCosmetic(True)
            item = self.canvas.scene().addRect(-4, -4, 8, 8, pen,
                                                  QColor("#ff5500" if index == self.selected_vertex else "#ffffff"))
            item.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIgnoresTransformations, True)
            item.setPos(*point)
            item.setZValue(30)
            self.handles.append((index, point, item))
        if record.geometry_type == 'polygon':
            points = record.geometry['points']
            for index, point in enumerate(points):
                other = points[(index + 1) % len(points)]
                midpoint = [(point[0] + other[0]) / 2, (point[1] + other[1]) / 2]
                item = self.canvas.scene().addRect(-3, -3, 6, 6, pen)
                item.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIgnoresTransformations, True)
                item.setPos(*midpoint)
                item.setZValue(29)
                self.midpoints.append((index, midpoint, item))

    def insert_vertex(self, position):
        record = self.selected_record()
        if record is None or record.geometry_type != 'polygon' or not self.can_edit(record):
            return False
        points = record.geometry['points']
        index, point, distance = nearest_polygon_segment(points, position)
        if distance**.5 * abs(self.canvas.transform().m11()) > 12:
            return False
        if any(sum((a-b)**2 for a,b in zip(point,p)) < 1e-12 for p in points):
            return False
        if self.edit_annotation(record.annotation_id, {'points': points[:index+1]+[point]+points[index+1:]}):
            self.selected_vertex = index+1
            self.refresh_selection()
            return True
        return False

    def delete_vertex(self):
        record = self.selected_record()
        if record is None or record.geometry_type != 'polygon' or not self.can_edit(record) or self.selected_vertex is None:
            return False
        points = record.geometry['points']
        if len(points) <= 3:
            self.message(tr('A polygon requires at least 3 vertices.'))
            return False
        index = self.selected_vertex
        self.selected_vertex = None
        return self.edit_annotation(record.annotation_id, {'points': points[:index]+points[index+1:]})

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

    def midpoint_at(self, position):
        cursor = self.canvas.mapFromScene(QPointF(*position))
        candidates = [(index, (cursor - self.canvas.mapFromScene(QPointF(*point))).manhattanLength())
                      for index, point, _ in self.midpoints]
        nearest = min(candidates, key=lambda pair: pair[1], default=(None, 100))
        return nearest[0] if nearest[1] <= 8 else None

    def hover_midpoint(self, position):
        hovered = self.midpoint_at(position)
        for index, _, item in self.midpoints:
            item.setBrush(QColor('#ffee88') if index == hovered else Qt.BrushStyle.NoBrush)

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
        for _, _, item in self.midpoints:
            self.canvas.scene().removeItem(item)
        self.midpoints.clear()

    def clear_preview(self):
        for item in self.preview:
            self.canvas.scene().removeItem(item)
        self.preview.clear()
        if getattr(self, 'tool', None) is not None:
            self.tool_settings.refresh()

    def preview_geometry(self, kind, geometry):
        self.clear_preview()
        pen = QPen(QColor("#ffcc33"), 2)
        pen.setCosmetic(True)
        item = self.canvas.overlays.renderers[kind](self.canvas.scene(), geometry, pen)
        item.setZValue(25)
        self.preview.append(item)

    def preview_polygon(self, points):
        self.tool_settings.refresh()
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

    def undo(self):
        if self.support_move.drag is not None:
            self.cancel()
            return
        draft = getattr(self.tool, "draft", None)
        if draft is not None and (draft.active or draft.history or draft.future):
            draft.undo()
        else:
            self.undo_stack.undo()

    def redo(self):
        if self.support_move.drag is not None:
            self.cancel()
            return
        draft = getattr(self.tool, "draft", None)
        if draft is not None and (draft.active or draft.history or draft.future):
            draft.redo()
        else:
            self.undo_stack.redo()

    def cancel(self):
        had_preview = bool(self.preview)
        if self.tool is not None:
            self.tool.cancel()
        self.clear_preview()
        self.refresh_selection()
        if had_preview:
            self.message('Cancelled.')

    def annotated_frame(self, direction):
        if not self.ready or self.document is None:
            return
        current = self.window.current_record.frame_index
        candidates = [i for i in self.document.annotated_frames() if (i-current)*direction > 0]
        if candidates:
            self.window.navigate(min(candidates) if direction > 0 else max(candidates))

    def default_path(self):
        queue = getattr(self.window, "queue_manager", None)
        if queue is not None:
            path = queue.annotation_path()
            if path is not None:
                return path
        return output_path('annotations') / (Path(self.document.cine_filename).stem + ".annotations.json")

    def save(self, path):
        if getattr(self.window, 'review_manager', None) and self.window.review_manager.active:
            raise ValueError('Use Save Reviewed Package As in portable review mode')
        self.workflow.flush_notes()
        if self.document is None:
            raise ValueError("No annotation document")
        queue = getattr(self.window, "queue_manager", None)
        if queue is not None and queue.root is not None:
            from ..sampling.sampler import outside_source
            outside_source(path, queue.root)
        self.document.save(path)
        self.path = Path(path)
        self.undo_stack.setClean()
        self.update_title()
        self.saved.emit(Path(path))

    def save_dialog(self, checked=False, save_as=False):
        if getattr(self.window, 'review_manager', None) and self.window.review_manager.active:
            return self.window.review_manager.save_dialog()
        if self.document is None:
            return False
        path = self.path
        if path is None or save_as:
            default = path or self.default_path()
            default.parent.mkdir(parents=True, exist_ok=True)
            filename, _ = QFileDialog.getSaveFileName(self.window, tr("Save Annotations"), str(default), tr("Annotation JSON (*.json)"))
            if not filename:
                return False
            path = Path(filename)
        try:
            self.save(path)
            self.message(tr("Annotations saved: ") + path.name)
            return True
        except Exception as error:
            self.window._error(tr("Annotation save failed: ") + str(error))
            return False

    def confirm_discard(self):
        if getattr(self.window, 'review_manager', None) and self.window.review_manager.active:
            return self.window.review_manager.confirm_discard()
        self.workflow.flush_notes()
        if self.document is None or not self.document.dirty:
            return True
        self.window.pause()
        answer = QMessageBox.warning(self.window, tr("Unsaved annotations"),
                                     tr("Save annotation changes before continuing?"),
                                     QMessageBox.StandardButton.Save | QMessageBox.StandardButton.Discard | QMessageBox.StandardButton.Cancel,
                                     QMessageBox.StandardButton.Cancel)
        if answer == QMessageBox.StandardButton.Save:
            return self.save_dialog()
        return answer == QMessageBox.StandardButton.Discard

    def load(self, path):
        if getattr(self.window, 'review_manager', None) and self.window.review_manager.active:
            raise ValueError('Package snapshots cannot be replaced by annotation JSON')
        if not self.ready:
            raise ValueError("Open a Cine and wait for a frame before loading annotations")
        document = AnnotationDocument.load(path)
        meta = self.window.metadata
        if not document.matches_cine(meta.filename, meta.file_size_bytes, meta.frame_count, meta.width, meta.height) or document.cine_id != self.window.current_record.cine_id:
            raise ValueError(tr("Annotation document does not match current Cine."))
        known_layers = {layer.layer_id for layer in self.window.layers}
        if not set(document.record_layers.values()) <= known_layers:
            raise ValueError(tr("Annotation document contains unavailable layers"))
        if not self.confirm_discard():
            return False
        self.cancel()
        self.document, self.path = document, Path(path)
        self.workflow.notes_pending = False
        if document.scheme:
            from copy import deepcopy
            self.workflow.scheme = deepcopy(document.scheme)
            self.workflow.scheme_selector.addItem(document.scheme['display_name'][current_language()], document.scheme)
            self.workflow.scheme_selector.setCurrentIndex(self.workflow.scheme_selector.count()-1)
            from ..annotations.schema import AnnotationLabel
            self.window.annotation_panel.replace_labels([AnnotationLabel(**row) for row in document.scheme['objects']['labels']])
            self.workflow.configure_display()
            self.workflow._build_states()
        self.selected_id = None
        self.undo_stack.clear()
        self.changed()
        return True

    def open_dialog(self):
        if not self.ready:
            return
        path, _ = QFileDialog.getOpenFileName(self.window, tr("Open Annotations"), str(output_path('annotations')), tr("Annotation JSON (*.json)"))
        if path:
            try:
                self.load(path)
            except Exception as error:
                self.window._error(str(error))

    def autosave(self):
        if getattr(self.window, 'review_manager', None) and self.window.review_manager.active:
            try:
                self.window.review_manager.autosave()
            except Exception as error:
                self.message(str(error))
            return
        self.workflow.flush_notes()
        if self.document is None or not self.document.dirty:
            return
        # Stable document UUID prevents two Cine files with the same stem overwriting recovery data.
        path = output_path('annotations/autosave') / (
            Path(self.document.cine_filename).stem + "." + self.document.document_id + ".annotations.autosave.json")
        queue = getattr(self.window, "queue_manager", None)
        if queue is not None and queue.annotation_path() is not None:
            path = queue.path.parent / "annotations/autosave" / path.name
        try:
            if queue is not None and queue.root is not None:
                from ..sampling.sampler import outside_source
                outside_source(path, queue.root)
            self.document.save(path, mark_saved=False)
        except Exception as error:
            self.message(tr("Annotation autosave failed: ") + str(error))
