"""Scheme selection and separate frame-level judgments for the annotation editor."""
from __future__ import annotations
from copy import deepcopy
from pathlib import Path
from uuid import uuid4
from PySide6.QtCore import Qt, QSignalBlocker
from PySide6.QtWidgets import (QGroupBox, QVBoxLayout, QHBoxLayout, QComboBox,
    QPushButton, QCheckBox, QTextEdit, QLabel, QLineEdit, QFileDialog, QMessageBox,
    QToolButton, QMenu, QDialog, QDialogButtonBox, QTableWidget, QTableWidgetItem)
from ..i18n import tr, current_language
from PySide6.QtGui import QAction
from ..widgets.wrapped_label import WrappedLabel
from ...annotations.display_style import resolve_display, ordered_ids
from ...annotations.scheme import load_scheme, save_custom_scheme, suggest_instance_name
from ...annotations.schema import AnnotationLabel
from ...annotations.frame_state import FrameStateRecord
from ..annotation_commands import SetFrameStateCommand


class CustomSchemeDialog(QDialog):
    """Only names/enabled flags are editable; the approved source remains untouched."""
    def __init__(self, scheme, parent):
        super().__init__(parent)
        self.setWindowTitle(tr('Save as custom scheme'))
        self.value = deepcopy(scheme)
        self.value['display'], _ = resolve_display(scheme, runtime=True)
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(tr('Approved baseline cannot be overwritten. Save a new custom scheme.')))
        self.name = QLineEdit(scheme['display_name'][current_language()])
        layout.addWidget(self.name)
        self.rows = ([('object', row) for row in self.value['objects']['labels']] +
                     [('state', row) for row in self.value['frame_states']['states']])
        self.table = QTableWidget(len(self.rows), 3)
        self.table.setHorizontalHeaderLabels(['Stable ID', tr('Display name'), tr('Enabled')])
        for index, (kind, row) in enumerate(self.rows):
            item = QTableWidgetItem(row['label_id' if kind == 'object' else 'state_id'])
            item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.table.setItem(index, 0, item)
            name = (self.value['display'].get('object_display_names', {}).get(row['label_id'], {}).get(current_language(), row['display_name']) if kind == 'object' else
                    self.value['display'].get('state_names', {}).get(row['state_id'], {}).get(current_language(),
                        row['display_name_zh' if current_language() == 'zh_CN' else 'display_name_en']))
            self.table.setItem(index, 1, QTableWidgetItem(tr(name) if kind == 'object' else name))
            enabled = QCheckBox()
            enabled.setChecked(row.get('enabled', True))
            self.table.setCellWidget(index, 2, enabled)
        layout.addWidget(self.table)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self.resize(650, 560)

    def custom_value(self):
        value = self.value
        value['scheme_id'] = 'droplet_annotation_scheme_custom_' + uuid4().hex[:12]
        value['status'] = 'custom'
        value['display_name'][current_language()] = self.name.text().strip() or value['scheme_id']
        for index, (kind, row) in enumerate(self.rows):
            field = ('display_name' if kind == 'object' else
                     'display_name_zh' if current_language() == 'zh_CN' else 'display_name_en')
            row[field] = self.table.item(index, 1).text().strip() or row[field]
            if kind == 'object':
                names = value['display'].setdefault('object_display_names', {}).setdefault(row['label_id'], {
                    'zh_CN': row['display_name'], 'en_US': row['display_name']})
                names[current_language()] = row[field]
            if kind == 'state':
                names = value['display'].setdefault('state_names', {}).setdefault(row['state_id'], {
                    'zh_CN': row['display_name_zh'], 'en_US': row['display_name_en']})
                names[current_language()] = row[field]
            row['enabled'] = self.table.cellWidget(index, 2).isChecked()
        return value


class WorkflowPanel:
    def __init__(self, editor):
        self.editor = editor
        self.window = editor.window
        self.panel = self.window.annotation_panel
        self.scheme = load_scheme()
        self.refreshing = False
        self.shown_frame = None
        self.notes_pending = False
        self.scheme_group = QGroupBox(tr('Annotation Scheme'))
        layout = QVBoxLayout(self.scheme_group)
        self.scheme_selector = QComboBox()
        self.scheme_selector.addItem(self.scheme['display_name'][current_language()], self.scheme)
        layout.addWidget(self.scheme_selector)
        row = QHBoxLayout()
        self.apply_button = QPushButton(tr('Apply'))
        self.modify_button = QPushButton(tr('Modify...'))
        self.load_button = QPushButton(tr('Open scheme...'))
        for button in (self.apply_button, self.modify_button, self.load_button):
            row.addWidget(button)
        layout.addLayout(row)
        self.active_label = WrappedLabel()
        self.active_label.setWordWrap(True)
        layout.addWidget(self.active_label)
        self.window.left_layout.insertWidget(2, self.scheme_group)
        drawing_group = self.drawing_group = QGroupBox(tr('Drawing Layer'))
        drawing_layout = QVBoxLayout(drawing_group)
        drawing_layout.addWidget(self.window.layer_panel.active_layer)
        drawing_layout.addWidget(self.window.layer_panel.drawing_into)
        visibility = QToolButton()
        visibility.setText(tr('Layer visibility and locks'))
        visibility.setCheckable(True)
        drawing_layout.addWidget(visibility)
        drawing_layout.addWidget(self.window.layer_panel)
        self.window.layer_panel.hide()
        visibility.toggled.connect(self.window.layer_panel.setVisible)
        self.panel.layout().insertWidget(0, drawing_group)

        self.instance_name = QLineEdit()
        self.instance_name.setPlaceholderText(tr('Optional instance name'))
        self.auto_name = QPushButton(tr('Auto name'))
        self.rename_button = QPushButton(tr('Apply name'))
        names = QHBoxLayout()
        names.addWidget(self.auto_name)
        names.addWidget(self.rename_button)
        object_layout = self.panel.labels_group.layout()
        object_layout.addWidget(QLabel(tr('Instance name')))
        object_layout.addWidget(self.instance_name)
        object_layout.addLayout(names)
        self.auto_name.clicked.connect(self.suggest_name)
        self.rename_button.clicked.connect(self.rename)
        self.instance_name.returnPressed.connect(self.rename)

        self.state_group = QGroupBox(tr('Frame State (multiple selection)'))
        self.state_layout = QVBoxLayout(self.state_group)
        self.quality_group = QGroupBox(tr('Judgment quality'))
        quality_layout = QVBoxLayout(self.quality_group)
        self.uncertain = QCheckBox(tr('Uncertain'))
        quality_layout.addWidget(self.uncertain)
        self.has_note = QCheckBox(tr('Has note'))
        quality_layout.addWidget(self.has_note)
        self.has_note.toggled.connect(self._has_note_changed)
        self.notes = QTextEdit()
        self.notes.setMaximumHeight(85)
        self.notes.setPlaceholderText(tr('Record uncertainty or items needing review...'))
        quality_layout.addWidget(self.notes)
        self.apply_notes = QPushButton(tr('Apply notes'))
        quality_layout.addWidget(self.apply_notes)
        records_index = self.panel.layout().indexOf(self.panel.records_group)
        self.panel.layout().insertWidget(records_index, self.state_group)
        self.panel.layout().insertWidget(records_index + 1, self.quality_group)
        self.checkboxes = {}
        self.configure_display()
        self._build_states()
        self.uncertain.toggled.connect(self._uncertain_changed)
        self.notes.textChanged.connect(self._notes_changed)
        self.apply_notes.clicked.connect(self.flush_notes)
        self.apply_button.clicked.connect(self.apply_scheme)
        self.modify_button.clicked.connect(self.modify_scheme)
        self.load_button.clicked.connect(self.open_scheme)
        self.refresh()

    def retranslate(self):
        """Only display text; do not apply schemes, flush notes or reset drafts."""
        with QSignalBlocker(self.scheme_selector):
            for index in range(self.scheme_selector.count()):
                scheme = self.scheme_selector.itemData(index)
                self.scheme_selector.setItemText(index, scheme['display_name'][current_language()])
        for row in self.scheme['frame_states']['states']:
            self.checkboxes[row['state_id']].setText(self.state_name(row))
        self._more_summary()
        self.panel.retranslate()

    def configure_display(self):
        review = getattr(self.window, 'review_manager', None)
        self.display, warning = resolve_display(self.scheme, runtime=not (review and review.active))
        self.panel.configure_display(self.display)
        self.active_label.setText(tr('Approved baseline') if self.scheme.get('status') == 'approved_baseline' else tr('Applied'))
        if warning:
            self.active_label.setText(tr('Display configuration error; safe defaults used.') + '\n' + warning)
            self.window.statusBar().showMessage(warning)

    def state_name(self, row):
        # Final catalog strings, not recursively translated composite text.
        names = self.display.get('state_names', {}).get(row['state_id'])
        if names:
            return names[current_language()]
        return row['display_name_zh' if current_language() == 'zh_CN' else 'display_name_en']

    def _build_states(self):
        while self.state_layout.count():
            item = self.state_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self.checkboxes.clear()
        self.more_actions = {}
        self.more_button = QToolButton()
        self.more_button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self.more_menu = QMenu(self.more_button)
        self.more_button.setMenu(self.more_menu)
        rows = {r['state_id']:r for r in self.scheme['frame_states']['states']}
        common = self.display.get('common_frame_states', [])
        for key in ordered_ids(list(rows), self.display.get('frame_state_order', [])):
            row = rows[key]
            if key in common:
                box = QCheckBox(self.state_name(row))
                self.state_layout.addWidget(box)
            else:
                box = QAction(self.state_name(row), self.more_menu)
                box.setCheckable(True)
                self.more_menu.addAction(box)
                self.more_actions[key] = box
            box.setEnabled(row['enabled'])
            box.toggled.connect(lambda checked, state_id=key: self.state_toggled(state_id, checked))
            self.checkboxes[key] = box
        self.state_layout.addWidget(self.more_button)
        self._more_summary()

    def _more_summary(self):
        count = sum(action.isChecked() for action in self.more_actions.values())
        self.more_button.setText(tr('More states') + (f' ({count})' if count else '') + ' ▾')

    def _notes_visibility(self):
        visible = self.uncertain.isChecked() or self.has_note.isChecked() or bool(self.notes.toPlainText())
        self.notes.setVisible(visible)
        self.apply_notes.setVisible(visible)

    def _uncertain_changed(self, checked):
        self._notes_visibility()
        self.commit_state()

    def _has_note_changed(self, checked):
        if self.refreshing:
            return
        if not checked and self.notes.toPlainText():
            box = QMessageBox(self.window)
            box.setWindowTitle(tr('Notes'))
            box.setText(tr('Notes contain text. Clear notes?'))
            keep = box.addButton(tr('Keep and show'), QMessageBox.ButtonRole.AcceptRole)
            clear = box.addButton(tr('Clear and hide'), QMessageBox.ButtonRole.DestructiveRole)
            box.addButton(QMessageBox.StandardButton.Cancel)
            box.exec()
            if box.clickedButton() is clear:
                self.notes.clear()
                self.flush_notes()
            else:
                with QSignalBlocker(self.has_note):
                    self.has_note.setChecked(True)
        self._notes_visibility()

    def state_toggled(self, key, checked):
        if self.refreshing:
            return
        exclusive = self.scheme['frame_states']['exclusive_state_id']
        if checked:
            for other, box in self.checkboxes.items():
                if other != key and (key == exclusive or other == exclusive):
                    blocker = QSignalBlocker(box)
                    box.setChecked(False)
                    del blocker
        self._more_summary()
        self.commit_state()

    def commit_state(self):
        editor = self.editor
        if self.refreshing or not editor.ready or editor.document is None:
            return
        frame = self.window.current_record
        old = editor.document.frame_state(frame.frame_index)
        values = dict(state_ids=tuple(key for key, box in self.checkboxes.items() if box.isChecked()),
                      uncertain=self.uncertain.isChecked(), notes=self.notes.toPlainText())
        if old and all(getattr(old, key) == value for key, value in values.items()):
            self.notes_pending = False
            return
        record = FrameStateRecord(frame.cine_id, frame.frame_index, frame.timestamp_time64,
                                  frame.timestamp_s, **values, derived_from=old.record_id if old else None)
        if hasattr(self.window, 'review_manager'):
            record = self.window.review_manager.record_state_provenance(record)
        self.notes_pending = False
        editor.undo_stack.push(SetFrameStateCommand(editor.document, record, editor.changed))

    def _notes_changed(self):
        self._notes_visibility()
        if not self.refreshing and self.editor.ready:
            self.notes_pending = True
            self.editor.update_title()

    def flush_notes(self):
        if self.notes_pending:
            self.commit_state()

    def refresh(self):
        self.refreshing = True
        try:
            ready = self.editor.ready and self.editor.document is not None
            self.state_group.setEnabled(ready)
            self.quality_group.setEnabled(ready)
            self.instance_name.setEnabled(ready)
            record = (self.editor.document.frame_state(self.window.current_record.frame_index) if ready else None)
            for key, box in self.checkboxes.items():
                box.setChecked(record is not None and key in record.state_ids)
            self.uncertain.setChecked(record.uncertain if record else False)
            if not self.notes_pending:
                self.notes.setPlainText(record.notes if record else '')
                with QSignalBlocker(self.has_note):
                    self.has_note.setChecked(bool(record and record.notes))
            self._notes_visibility()
            self._more_summary()
        finally:
            self.refreshing = False

    def suggest_name(self):
        label = self.panel.selected_label()
        if label and self.editor.ready:
            self.instance_name.setText(suggest_instance_name(self.editor.document,
                self.window.current_record.frame_index, label.label_id, self.scheme.get('instance_prefixes', {})))

    def rename(self):
        self.editor.rename_selected(self.instance_name.text())

    def apply_scheme(self):
        self.flush_notes()
        self.editor.cancel()
        self.scheme = deepcopy(self.scheme_selector.currentData())
        labels = [AnnotationLabel(**row) for row in self.scheme['objects']['labels']]
        self.panel.replace_labels(labels)
        self.configure_display()
        self._build_states()
        self.editor.taxonomy_metadata = {'scheme_id': self.scheme['scheme_id'], 'version': self.scheme['version']}
        if self.editor.document is not None:
            self.editor.document.scheme = deepcopy(self.scheme)
            self.editor.document._touch('apply_scheme', scheme_id=self.scheme['scheme_id'])
        self.editor.changed()
        self.editor.label_changed()

    def open_scheme(self):
        path, _ = QFileDialog.getOpenFileName(self.window, tr('Open scheme...'), 'outputs/annotation_schemes', 'JSON (*.json)')
        if path:
            try:
                value = load_scheme(path)
                self.scheme_selector.addItem(value['display_name'][current_language()], value)
                self.scheme_selector.setCurrentIndex(self.scheme_selector.count() - 1)
            except Exception as error:
                self.window._error(str(error))

    def modify_scheme(self):
        dialog = CustomSchemeDialog(self.scheme_selector.currentData(), self.window)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        value = dialog.custom_value()
        path, _ = QFileDialog.getSaveFileName(self.window, tr('Save as custom scheme'),
                                             'outputs/annotation_schemes/' + value['scheme_id'] + '.json', 'JSON (*.json)')
        if path:
            try:
                save_custom_scheme(value, path)
                self.scheme_selector.addItem(value['display_name'][current_language()], value)
                self.scheme_selector.setCurrentIndex(self.scheme_selector.count() - 1)
            except Exception as error:
                self.window._error(str(error))
