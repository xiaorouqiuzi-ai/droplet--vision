"""One screen-space handle for sparse, manual support-template alignment."""
from copy import deepcopy
from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QColor, QPainterPath, QPen
from PySide6.QtWidgets import QGraphicsItem, QWidget, QVBoxLayout, QLabel, QPushButton
from ..annotations import AnnotationRecord
from ..annotations.support_translation import group_bounds, bounded_delta, translated
from .annotation_commands import SetSupportRodTranslationCommand, SupportGeometryCommand
from .i18n import tr


class SupportRodMove:
    def __init__(self, editor):
        self.editor = editor
        self.item = None
        self.drag = None
        self.panel = QWidget()
        layout = QVBoxLayout(self.panel)
        layout.setContentsMargins(0,0,0,0)
        self.offset_label = QLabel()
        self.offset_label.setWordWrap(True)
        self.reset_button = QPushButton()
        self.reset_button.clicked.connect(self.reset)
        layout.addWidget(self.offset_label)
        layout.addWidget(self.reset_button)

    @property
    def review(self):
        review = getattr(self.editor.window, 'review_manager', None)
        return bool(review and review.active)

    def group(self):
        editor = self.editor
        if not editor.ready or editor.document is None or editor.window.current_record is None:
            return []
        frame = editor.window.current_record.frame_index
        if self.review and not editor.document.support_templates.get('support_structure', {}).get('enabled'):
            return [r for r in editor.document.support_copies(frame) if r.geometry_type == 'polygon']
        return editor.document.support_group(frame)

    def eligible(self):
        editor = self.editor
        records = self.group()
        selected = editor.selected_record()
        label = editor.window.annotation_panel.selected_label()
        return bool(records and editor.tool_key == 'select'
                    and ((selected and selected.label_id == 'support_structure')
                         or (label and label.label_id == 'support_structure'))
                    and all(editor.can_edit(r) and r.annotation_id not in editor.hidden_ids()
                            and r.annotation_id in editor.canvas.overlays.by_id for r in records))

    def full(self, records):
        doc = self.editor.document
        source_ids = doc.support_templates.get('support_structure', {}).get('annotation_ids', [])
        return (self.review and not doc.support_templates.get('support_structure', {}).get('enabled')) or any(r.annotation_id in doc.active_annotation_ids and r.annotation_id not in source_ids for r in records)

    def clear_handle(self):
        if self.item is not None:
            self.editor.canvas.scene().removeItem(self.item)
            self.item = None

    def refresh(self):
        self.refresh_panel()
        if self.drag is not None:
            self.preview(self.drag['delta'])
            return
        self.clear_handle()
        if not self.eligible():
            return
        left, top, right, bottom = group_bounds(self.group())
        center = QPointF((left+right)/2, (top+bottom)/2)
        path = QPainterPath()
        # 16 px four-way arrow, deliberately unlike vertex/midpoint squares.
        for a,b in [((-8,0),(8,0)), ((0,-8),(0,8)),
                    ((-8,0),(-5,-3)),((-8,0),(-5,3)),((8,0),(5,-3)),((8,0),(5,3)),
                    ((0,-8),(-3,-5)),((0,-8),(3,-5)),((0,8),(-3,5)),((0,8),(3,5))]:
            path.moveTo(*a);path.lineTo(*b)
        self.item = self.editor.canvas.scene().addPath(path, QPen(QColor('#ffe066'),2))
        self.item.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIgnoresTransformations)
        self.item.setPos(center)
        self.item.setZValue(40)
        self.item.setToolTip(tr('Drag to translate the support rod for this frame'))
        self.item.setCursor(Qt.CursorShape.SizeAllCursor)

    def refresh_panel(self):
        editor = self.editor
        label = editor.window.annotation_panel.selected_label()
        selected = editor.selected_record()
        visible = bool(editor.ready and editor.document and editor.tool_key == 'select'
                       and ((label and label.label_id == 'support_structure')
                            or (selected and selected.label_id == 'support_structure')))
        self.panel.setVisible(visible)
        self.reset_button.setText(tr('Reset frame position'))
        if not visible:
            return
        frame = editor.window.current_record.frame_index
        offset = editor.document.support_translation(frame)
        full = self.full(self.group())
        if self.drag is not None and not self.drag['full']:
            offset = {key:self.drag['offset'][key]+self.drag['delta'][key] for key in ('dx','dy')}
        self.offset_label.setText(tr('Frame override') if full else
            tr('Frame offset: X: {dx:+.3f} px | Y: {dy:+.3f} px').format(**offset))
        self.reset_button.setEnabled(not full and bool(offset['dx'] or offset['dy']) and self.eligible())
        if self.item is not None:
            self.item.setToolTip(tr('Drag to translate the support rod for this frame'))

    def hit(self, position):
        if self.item is None or not self.eligible():
            return False
        view = self.editor.canvas
        delta = view.mapFromScene(QPointF(*position)) - view.mapFromScene(self.item.pos())
        return abs(delta.x()) <= 10 and abs(delta.y()) <= 10

    def press(self, position):
        if not self.hit(position):
            return False
        editor = self.editor
        editor.window.pause()
        frame = editor.window.current_record.frame_index
        records = self.group()
        self.drag = {'start':position, 'records':records, 'full':self.full(records),
                     'offset':editor.document.support_translation(frame), 'delta':{'dx':0.0,'dy':0.0},
                     'center':QPointF(self.item.pos())}
        editor.clear_handles()
        if frame == editor.document.support_templates.get('support_structure', {}).get('source_frame_index'):
            editor.message('This is the template source frame. Moving affects this frame only, not the template.')
        return True

    def move(self, position):
        if self.drag is None:
            return
        doc = self.editor.document
        dx,dy = position[0]-self.drag['start'][0],position[1]-self.drag['start'][1]
        self.preview(bounded_delta(self.drag['records'],dx,dy,doc.width,doc.height))
        self.refresh_panel()

    def preview(self, delta):
        self.drag['delta'] = delta
        for record in self.drag['records']:
            item = self.editor.canvas.overlays.by_id.get(record.annotation_id)
            if item is not None:
                item.setPos(delta['dx'],delta['dy'])
        if self.item is not None:
            self.item.setPos(self.drag['center'] + QPointF(delta['dx'],delta['dy']))

    def release(self, position):
        if self.drag is None:
            return
        self.move(position)
        state = self.drag
        delta = dict(state['delta'])
        self.cancel()
        if delta['dx'] or delta['dy']:
            editor = self.editor
            editor.window.review_manager.begin_edit()
            if state['full']:
                self.commit_geometry(state['records'], {r.annotation_id:translated(r.geometry,delta) for r in state['records']})
            else:
                offset = {key:state['offset'][key]+delta[key] for key in ('dx','dy')}
                sources = [editor.document.records.get(key) for key in
                           editor.document.support_templates['support_structure']['annotation_ids']]
                offset = bounded_delta(sources, offset['dx'], offset['dy'], editor.document.width, editor.document.height)
                editor.undo_stack.push(SetSupportRodTranslationCommand(editor.document,
                    editor.window.current_record.frame_index, offset, editor.changed))
        self.editor.refresh_selection()

    def cancel(self):
        if self.drag is not None:
            self.preview({'dx':0.0,'dy':0.0})
            self.drag = None

    def reset(self):
        self.cancel()
        if not self.eligible() or self.full(self.group()):
            return
        editor = self.editor
        frame = editor.window.current_record.frame_index
        if any(editor.document.support_translation(frame).values()):
            editor.window.review_manager.begin_edit()
            editor.undo_stack.push(SetSupportRodTranslationCommand(editor.document, frame,
                                   {'dx':0.0,'dy':0.0}, editor.changed))

    def materialize_edit(self, annotation_id, geometry, attributes=None):
        records = self.group()
        if not any(r.annotation_id == annotation_id for r in records):
            return False
        return self.commit_geometry(records, {annotation_id:geometry}, annotation_id, attributes)

    def commit_geometry(self, records, geometries, selected=None, attributes=None):
        """Consume translation into a complete group in one undo action."""
        editor = self.editor
        doc, frame = editor.document, editor.window.current_record
        source_ids = doc.support_templates.get('support_structure', {}).get('annotation_ids', [])
        rows = []
        for original in records:
            if not editor.can_edit(original):
                return False
            geometry = deepcopy(geometries.get(original.annotation_id, original.geometry))
            old_id = original.annotation_id if original.annotation_id in doc.active_annotation_ids and original.annotation_id not in source_ids else None
            if old_id:
                record = doc.derive(old_id,geometry)
                layer_id = 'reviewed' if self.review else doc.record_layers[old_id]
            else:
                record = AnnotationRecord(doc.cine_id,frame.frame_index,'support_structure','polygon',geometry,
                                          attributes=deepcopy(original.attributes))
                layer_id = 'manual'
            source_id = doc.support_source_id(original) or original.attributes.get('template_source_annotation_id')
            record.attributes.update(creation_tool=(doc.support_scope.kind if source_ids else 'cine') + '_support_template_override',
                                     template_source_annotation_id=source_id,
                                     template_source_frame_index=(doc.records.get(source_id).frame_index if source_id in doc.record_layers
                                                                  else original.attributes.get('template_source_frame_index')),
                                     raw_time64=frame.timestamp_time64, relative_timestamp_s=frame.timestamp_s,
                                     display_mode_used=editor.window.display_panel.settings.mode)
            offset = record.attributes.pop('frame_translation', None)
            if offset:
                record.attributes['materialized_frame_translation'] = offset
            if original.annotation_id == selected:
                record.attributes.update(attributes or {})
            editor.window.review_manager.prepare_record(record)
            layer = next((layer for layer in editor.window.layers if layer.layer_id == layer_id), None)
            if layer is None or layer.locked:
                return False
            try:
                doc.validate_record(record)
            except ValueError as error:
                editor.message(str(error))
                return False
            rows.append((old_id, record, layer_id))
        templates = doc.support_templates if self.review and not doc.support_templates else doc.with_support_translation(frame.frame_index, {'dx':0.0,'dy':0.0})
        for original, (_, record, _) in zip(records,rows):
            if original.annotation_id == (selected or editor.selected_id):
                editor.selected_id = record.annotation_id
        editor.undo_stack.push(SupportGeometryCommand(doc,rows,templates,editor.changed))
        return True
