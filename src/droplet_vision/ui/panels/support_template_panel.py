"""Cine-local static projection controls; no per-frame duplication."""
from PySide6.QtCore import QSignalBlocker
from PySide6.QtWidgets import QWidget, QVBoxLayout, QCheckBox, QPushButton
from ..widgets.wrapped_label import WrappedLabel
from ..i18n import tr
from ..annotation_commands import SetCineTemplateCommand


class SupportTemplateControls(QWidget):
    def __init__(self, editor):
        super().__init__()
        self.editor, self.window = editor, editor.window
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 3, 0, 0)
        self.apply = QCheckBox()
        self.set_button = QPushButton()
        self.info = WrappedLabel()
        for widget in (self.apply, self.set_button, self.info):
            layout.addWidget(widget)
        self.apply.clicked.connect(self.apply_current)
        self.set_button.clicked.connect(self.set_template)

    def available(self):
        return bool(self.editor.ready and self.editor.document is not None
                    and self.window.current_record is not None
                    and not (getattr(self.window, 'review_manager', None) and self.window.review_manager.active))

    def sources(self):
        if not self.available():
            return []
        return [r for r in self.editor.document.active_records(self.window.current_record.frame_index)
                if r.label_id == 'support_structure' and r.geometry_type == 'polygon'
                and r.source == 'manual' and self.editor.can_edit(r)]

    def refresh(self):
        label = self.window.annotation_panel.selected_label()
        self.setVisible(bool(label and label.label_id == 'support_structure'))
        doc = self.editor.document
        template = doc.cine_templates.get('support_structure') if doc else None
        self.apply.setText(tr('Apply to entire Cine'))
        with QSignalBlocker(self.apply):
            self.apply.setChecked(bool(template and template.get('apply_entire_cine')))
        self.apply.setEnabled(self.available() and bool(template or self.sources()))
        self.apply.setToolTip(tr('Apply one static template without creating per-frame records.') if self.apply.isEnabled()
                             else tr('Create at least one confirmed support-rod annotation first.'))
        self.set_button.setText(tr('Update Cine Support Rod Template') if template else tr('Set as Cine Support Rod Template'))
        self.set_button.setEnabled(bool(self.sources()))
        self.set_button.setToolTip(tr('Use all confirmed editable support rod polygons on the current frame.'))
        self.info.setText(tr('Support rod template: not set') if not template else
                          tr('Support rod template: set | Source frame: {frame} | Count: {count}').format(
                              frame=template['source_frame_index'], count=len(template['annotation_ids'])))

    def set_template(self):
        sources = self.sources()
        if not sources:
            return
        self.window.pause()
        doc = self.editor.document
        value = doc.support_template_from([r.annotation_id for r in sources])
        value['support_structure']['apply_entire_cine'] = doc.cine_templates.get('support_structure', {}).get('apply_entire_cine', False)
        self.editor.undo_stack.push(SetCineTemplateCommand(doc, value, self.editor.changed))
        self.editor.message('Cine support rod template updated from current-frame polygons.')

    def apply_current(self, checked):
        if not self.available():
            self.refresh()
            return
        self.window.pause()
        doc = self.editor.document
        value = doc.cine_templates
        if not value:
            sources = self.sources()
            if not checked or not sources:
                self.refresh()
                return
            value = doc.support_template_from([r.annotation_id for r in sources])
        if value['support_structure'].get('apply_entire_cine', False) != checked:
            value['support_structure']['apply_entire_cine'] = checked
            self.editor.undo_stack.push(SetCineTemplateCommand(doc, value, self.editor.changed))
        self.refresh()
