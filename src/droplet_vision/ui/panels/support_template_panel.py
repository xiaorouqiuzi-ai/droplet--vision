"""Scope-aware static projection controls; no per-frame duplication."""
from PySide6.QtCore import QSignalBlocker
from PySide6.QtWidgets import QWidget, QVBoxLayout, QCheckBox, QPushButton, QMessageBox
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
        self.set_button.clicked.connect(lambda: self.set_template(confirm=True))
        self.window.annotation_panel.support_actions = self.context_actions

    def available(self):
        return bool(self.editor.ready and self.editor.document is not None
                    and self.window.current_record is not None)

    def sources(self):
        if not self.available():
            return []
        return [r for r in self.editor.document.active_records(self.window.current_record.frame_index)
                if r.label_id == 'support_structure' and r.geometry_type == 'polygon'
                and r.annotation_id not in self.editor.document.support_suppressed_ids(self.window.current_record.frame_index)
                and r.source == 'manual' and self.editor.can_edit(r)]

    def refresh(self):
        label = self.window.annotation_panel.selected_label()
        self.setVisible(bool(label and label.label_id == 'support_structure'))
        doc = self.editor.document
        template = doc.support_templates.get('support_structure') if doc else None
        package = bool(doc and doc.support_scope.kind == 'package')
        self.apply.setText(tr('Apply to entire package' if package else 'Apply to entire Cine'))
        with QSignalBlocker(self.apply):
            self.apply.setChecked(bool(template and template.get(doc.support_enabled_key)))
        self.apply.setEnabled(self.available() and bool(template or self.sources()))
        self.apply.setToolTip(tr('Apply one static template without creating per-frame records.') if self.apply.isEnabled()
                             else tr('Create at least one confirmed support-rod annotation first.'))
        self.set_button.setText(tr('Update package support-rod template' if package else 'Update Cine Support Rod Template') if template else
                                tr('Set as package support-rod template' if package else 'Set as Cine Support Rod Template'))
        self.set_button.setEnabled(bool(self.sources()))
        self.set_button.setToolTip(tr('Use all confirmed editable support rod polygons on the current frame.'))
        self.info.setText(tr('Support rod template: not set') if not template else
                          tr('Support rod template: set | Source frame: {frame} | Count: {count}').format(
                              frame=template['source_frame_index'], count=len(template['annotation_ids'])))

    def set_template(self, *, apply=False, confirm=False):
        sources = self.sources()
        if not sources:
            return
        self.window.pause()
        doc = self.editor.document
        if confirm and doc.support_templates and not self.confirm_replace():
            return
        value = doc.support_template_from([r.annotation_id for r in sources])
        value['support_structure'][doc.support_enabled_key] = apply or doc.support_templates.get('support_structure', {}).get(doc.support_enabled_key, False)
        self.window.review_manager.begin_edit()
        self.editor.undo_stack.push(SetCineTemplateCommand(doc, value, self.editor.changed))
        self.editor.message('Support rod template updated for the current scope.')

    def apply_current(self, checked):
        if not self.available():
            self.refresh()
            return
        self.window.pause()
        doc = self.editor.document
        value = doc.support_templates
        if not value:
            sources = self.sources()
            if not checked or not sources:
                self.refresh()
                return
            value = doc.support_template_from([r.annotation_id for r in sources])
        if value['support_structure'].get(doc.support_enabled_key, False) != checked:
            self.window.review_manager.begin_edit()
            value['support_structure'][doc.support_enabled_key] = checked
            self.editor.undo_stack.push(SetCineTemplateCommand(doc, value, self.editor.changed))
        self.refresh()

    def confirm_replace(self):
        box = QMessageBox(self.window)
        box.setWindowTitle(tr('Confirm'))
        box.setText(tr('A support-rod template already exists. Replace it with the current annotations?'))
        replace = box.addButton(tr('Replace template'), QMessageBox.ButtonRole.AcceptRole)
        box.addButton(QMessageBox.StandardButton.Cancel)
        box.exec()
        return box.clickedButton() == replace

    def context_actions(self, menu, annotation_id):
        doc = self.editor.document
        if not self.available():
            return
        projection = self.editor.projections().get(annotation_id)
        record = projection or (doc.records.get(annotation_id) if annotation_id in doc.active_annotation_ids else None)
        if record is None or record.label_id != 'support_structure':
            return
        package = doc.support_scope.kind == 'package'
        if projection is not None:
            menu.addAction(tr('Disable package-wide application' if package else 'Disable Cine-wide application'),
                           lambda: self.apply_current(False))
        else:
            action = menu.addAction(tr('Set as support-rod template and apply to entire package' if package else
                                       'Set as support-rod template and apply to entire Cine'),
                                   lambda: self.set_template(apply=True, confirm=True))
            action.setEnabled(self.editor.can_edit(record) and bool(self.sources()))
            action.setToolTip(tr('Use all confirmed editable support rod polygons on the current frame.'))
            update = menu.addAction(tr('Update package support-rod template' if package else 'Update Cine Support Rod Template'),
                                    lambda: self.set_template(confirm=True))
            update.setEnabled(self.editor.can_edit(record) and bool(doc.support_templates) and bool(self.sources()))
        reset = menu.addAction(tr('Reset frame position'), lambda: self.reset_frame(annotation_id))
        frame = self.window.current_record.frame_index
        reset.setEnabled(self.editor.can_edit(record) and any(doc.support_translation(frame).values())
                         and not doc.support_full_overrides(frame))

    def reset_frame(self, annotation_id):
        self.editor.switch_tool('select')
        self.editor.select(annotation_id)
        self.editor.support_move.reset()
