"""Portable review adapter for the existing annotation editor, not a second editor."""
from __future__ import annotations
from copy import deepcopy
from dataclasses import replace
import json
import os
import stat
from pathlib import Path
from ..resources import output_path

from PySide6.QtCore import QObject, QThreadPool, QSignalBlocker
from PySide6.QtGui import QUndoCommand
from PySide6.QtWidgets import (QDialog, QDialogButtonBox, QVBoxLayout, QFormLayout, QComboBox,
    QSpinBox, QCheckBox, QLineEdit, QLabel, QGroupBox, QPushButton, QFileDialog, QInputDialog,
    QMessageBox, QProgressDialog, QTextEdit, QScrollArea, QWidget)

from ..annotations import AnnotationDocument, ViewerSession
from ..annotations.schema import AnnotationLabel, _now
from ..annotations.scheme import load_scheme
from ..cine.metadata import CineMetadata
from ..cine.timing import TimingSummary
from ..schema import FrameResult, TimingStatus
from ..display.photometric import PhotometricReference
from ..review_package import ReviewPackage, ReviewFrameProvider, merge_review, review_decision
from ..review_package.cine_export import export_cines
from ..sampling.schema import resolve_relative
from .branding import project_metadata
from .cine_controller import _Task
from .viewer_state import ViewerState
from .widgets.wrapped_label import WrappedLabel
from .i18n import tr, current_language


class ExportReviewDialog(QDialog):
    def __init__(self, parent):
        super().__init__(parent)
        self.setWindowTitle(tr('Create Annotation Package from Current Annotations...'))
        form = QFormLayout(self)
        self.selection = QComboBox()
        for key, title in [('current','Current frame'), ('human','All human-annotated frames'), ('queue','Queue status selection')]:
            self.selection.addItem(tr(title), key)
        form.addRow(tr('Review targets'), self.selection)
        self.context = QSpinBox()
        self.context.setRange(0,100)
        self.context.setValue(5)
        form.addRow(tr('Context frames before / after'), self.context)
        self.creator = QLineEdit()
        form.addRow(tr('Creator (optional alias)'), self.creator)
        self.purpose = QComboBox()
        for title, key in [('New annotation task','annotation'), ('Review task','review'), ('General','general')]:
            self.purpose.addItem(tr(title), key)
        form.addRow(tr('Purpose'), self.purpose)
        self.statuses = {}
        for status in ('DONE', 'NEEDS_REVIEW', 'PENDING', 'IN_PROGRESS', 'SKIPPED'):
            box = QCheckBox(status)
            box.setChecked(status in ('DONE','NEEDS_REVIEW'))
            self.statuses[status] = box
            form.addRow(box)
        self.folder = QCheckBox(tr('Export as unpacked folder'))
        form.addRow(self.folder)
        hint = QLabel(tr('Raw PNGs only. Context frames are not review targets. No Cine is included.'))
        hint.setWordWrap(True)
        form.addRow(hint)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        form.addRow(buttons)


class ConflictDialog(QDialog):
    def __init__(self, conflicts, parent):
        super().__init__(parent)
        self.setWindowTitle(tr('Review conflicts — explicit choice required'))
        layout = QVBoxLayout(self)
        self.choices = {}
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        body = QWidget()
        choices_layout = QVBoxLayout(body)
        scroll.setWidget(body)
        layout.addWidget(scroll)
        for conflict in conflicts:
            text = QTextEdit()
            text.setReadOnly(True)
            text.setPlainText(json.dumps({k:conflict[k] for k in ('frame_index','base','local','reviewer')}, indent=2, ensure_ascii=False))
            text.setMinimumHeight(160)
            choices_layout.addWidget(text)
            combo = QComboBox()
            for key, title in [(None,'Choose a resolution'), ('local','Keep local'), ('reviewer','Use reviewer as Reviewed candidate'),
                               ('both','Keep both as Reviewed candidates'), ('defer','Defer')]:
                combo.addItem(tr(title), key)
            choices_layout.addWidget(combo)
            self.choices[conflict['conflict_id']] = combo
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept_checked)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self.resize(680,600)

    def accept_checked(self):
        if any(c.currentData() is None for c in self.choices.values()):
            QMessageBox.warning(self, tr('Warning'), tr('Choose a resolution for every conflict.'))
            return
        self.accept()


class ReviewController:
    """Synchronous small-PNG adapter; deliberately has no CineReader."""
    def __init__(self, owner):
        self.owner = owner
        self.state = ViewerState()
        self.photometric = None
        self.photometric_error = None

    def request_frame(self, index):
        owner = self.owner
        row = owner.provider.metadata.get((owner.cine_id,index))
        if row is None:
            owner.window.timeline.set_frame(self.state.frame_index)
            owner.window.pause()
            owner.window.statusBar().showMessage(tr('This frame is not included in the annotation package.'))
            return
        pixels = owner.provider.get_frame(owner.cine_id,index)
        self.state.request(index)
        record = FrameResult(owner.cine_id,index,timestamp_s=row['relative_timestamp_s'],
                             timestamp_time64=row['raw_time64'],timing_status=TimingStatus(row['timing_status']))
        owner.window._frame_ready(index,pixels,record)
        owner.refresh()

    def recalculate_reference(self):
        self.owner.window.statusBar().showMessage(tr('Package mode uses the exported locked display gain.'))

    def close(self):
        self.state.frame_count = 0

    def shutdown(self):
        self.owner.normal_controller.shutdown()


class DecisionCommand(QUndoCommand):
    def __init__(self, owner, kind, record_id, status):
        super().__init__(tr('Review decision'))
        self.owner, self.kind, self.record_id, self.status = owner,kind,record_id,status
        self.doc = owner.window.editor.document
        self.before = (set(self.doc.active_annotation_ids), self.doc.active_frame_state_records)
        self.after = None

    def restore(self, value):
        active, states = value
        self.doc.transition(activate=active-set(self.doc.active_annotation_ids), deactivate=set(self.doc.active_annotation_ids)-active)
        for index in set(states) | set(self.doc.active_frame_state_records):
            self.doc.activate_frame_state(index,states.get(index))
        self.owner.window.editor.changed()

    def redo(self):
        if self.after is None:
            review_decision(self.owner.package,self.doc.cine_id,self.kind,self.record_id,self.status)
            self.decision = self.owner.package.review['decisions'][-1]
            self.after = (set(self.doc.active_annotation_ids),self.doc.active_frame_state_records)
        else:
            self.owner.package.review['decisions'].append(self.decision)
            self.restore(self.after)
        self.owner.window.editor.changed()

    def undo(self):
        self.owner.package.review['decisions'].remove(self.decision)
        self.restore(self.before)


class ReviewCoordinator(QObject):
    def __init__(self, window):
        super().__init__(window)
        self.window = window
        self.normal_controller = window.controller
        self.controller = ReviewController(self)
        self.package = self.provider = self.cine_id = None
        self.completed_revisions = None
        self.completed_work = self.completion_time = None
        self.reviewer = ''
        self.review_started = False
        self.task = None
        self.batch_window = None
        self.pool = QThreadPool(self)
        self.pool.setMaxThreadCount(1)
        self.panel = QGroupBox(tr('Annotation Package'))
        layout = QVBoxLayout(self.panel)
        self.info = WrappedLabel()
        self.info.setProperty('literal_text',True)
        layout.addWidget(self.info)
        self.cines = QComboBox()
        self.cines.currentIndexChanged.connect(self._select_cine)
        layout.addWidget(self.cines)
        for title, action in [('Previous available frame',lambda:self.adjacent(-1)),
            ('Next available frame',lambda:self.adjacent(1)),('Previous review target',lambda:self.adjacent(-1,True)),
            ('Next review target',lambda:self.adjacent(1,True)),('Accept selected object',lambda:self.decide('object','accepted')),
            ('Reject selected object',lambda:self.decide('object','rejected')),
            ('Accept frame state',lambda:self.decide('state','accepted')),('Reject frame state',lambda:self.decide('state','rejected')),
            ('Frame state needs review',lambda:self.decide('state','needs_review')),
            ('Review note...',self.note),('Mark frame reviewed',self.mark_frame),('Complete review',self.complete)]:
            button = QPushButton(tr(title))
            button.clicked.connect(action)
            layout.addWidget(button)
        window.left_layout.insertWidget(0,self.panel)
        self.panel.hide()
        functions = window.menuBar().addMenu(tr('Functions'))
        window.functions_menu = functions
        self.uniform_action = window._action(functions, 'Create Annotation Package from Uniform Cine Sampling...', self.uniform_dialog)
        self.batch_action = window._action(functions, 'Create Annotation Packages from Folder...', self.batch_dialog)
        self.batch_action.setToolTip(tr('Recursively sample Cine files into annotation packages while preserving the folder tree.'))
        self.export_action = window._action(functions,'Create Annotation Package from Current Annotations...',self.export_dialog)
        window._action(functions,'Open Annotation Package...',self.open_dialog)
        window._action(functions,'Open Annotation Package Folder...',lambda:self.open_dialog(folder=True))
        self.save_action = window._action(functions,'Save Annotation Package As...',self.save_dialog)
        self.import_action = window._action(functions,'Import Returned Annotation Package...',self.import_dialog)
        window.transport.save_package.clicked.connect(self.quick_save)
        self.refresh()

    @property
    def active(self):
        return self.package is not None

    def refresh(self):
        self.refresh_save_button()
        self.uniform_action.setEnabled(self.task is None)
        self.save_action.setEnabled(self.active)
        self.export_action.setEnabled(not self.active)
        self.import_action.setEnabled(not self.active)
        if not self.active or not self.cine_id:
            return
        doc = self.package.documents[self.cine_id]
        self.info.setText(tr('Package: {name}\nOriginal Cine: {cine}\nOriginal frames: {total}\nAvailable packaged frames: {available}\nStatus: {status}').format(
            name=self.package.path.name if self.package.path else self.package.manifest['package_id'],
            cine=doc.cine_filename,total=doc.frame_count,available=len(self.provider.available(self.cine_id)),
            status=self.package.manifest['package_status']))
        self.info.setText(self.info.text() + '\n' + tr('Unsaved changes' if self.dirty else 'Saved'))
        total, done, remaining = self.package.progress(self.cine_id)
        self.info.setText(self.info.text() + '\n' + tr('Targets: {total} | Annotated / reviewed: {done} | Remaining: {remaining}').format(
            total=total, done=done, remaining=remaining))
        self.window.timeline.slider.set_package_markers(self.provider.available(self.cine_id),self.provider.available(self.cine_id,True))
        self.window.display_panel.recalculate_button.setEnabled(False)
        self.window.editor.update_title()

    @property
    def dirty(self):
        return self.active and (self.package.dirty or self.window.editor.workflow.notes_pending)

    def refresh_save_button(self):
        button = self.window.transport.save_package
        button.setVisible(bool(self.dirty))
        path = self.package.path if self.active else None
        direct = path is not None and not path.is_dir() and path.suffix.lower() == '.dvapkg'
        button.setText(tr('Save Annotation Package' if direct else 'Save as New Annotation Package'))
        button.setToolTip(tr('Save changes to the currently opened annotation package' if direct
                            else 'Legacy files and package folders use Save As to preserve the original.'))

    def begin_edit(self):
        if self.active and not self.review_started:
            self.package.start_review(self.reviewer, project_metadata()[0])
            self.review_started = True

    def open_dialog(self, checked=False, folder=False):
        path = (QFileDialog.getExistingDirectory(self.window,tr('Open Annotation Package Folder...')) if folder else
                QFileDialog.getOpenFileName(self.window,tr('Open Annotation Package...'),str(output_path('annotation_packages')),'Droplet Vision Annotation Package (*.dvapkg *.dvrpkg)')[0])
        if not path:
            return
        try:
            package = ReviewPackage.open(path)  # Integrity errors appear before leaving current work.
            name, ok = QInputDialog.getText(self.window,tr('Reviewer'),tr('Reviewer name (optional alias)'),
                                           text=package.review.get('reviewer',{}).get('display_name',''))
            if ok:
                self.open(package,name)
        except Exception as error:
            self.window._error(str(error))

    def open(self, package, reviewer=''):
        if not self.window.editor.confirm_discard():
            return False
        self.leave()
        self.window._reset()
        self.normal_controller.close()  # Invalidates any pending async Cine result.
        self.previous_scheme = deepcopy(self.window.editor.workflow.scheme)
        self.package, self.provider = package, ReviewFrameProvider(package)
        self.reviewer, self.review_started = reviewer, False
        self.completed_work = package.work_fingerprint() if package.manifest['package_status'] == 'reviewed' else None
        self.completion_time = package.review.get('review_completed_at')
        self.window.controller = self.controller
        self.window.cine_path = None
        self.window.queue_manager.pending = self.window.queue_manager.current_id = None
        with QSignalBlocker(self.cines):
            self.cines.clear()
            for cine, doc in package.documents.items():
                self.cines.addItem(doc.cine_filename,cine)
        self.panel.show()
        self.switch_cine(next(iter(package.documents)))
        return True

    def leave(self):
        if not self.active:
            return
        self.window.controller = self.normal_controller
        self.package = self.provider = self.cine_id = None
        self.panel.hide()
        self.window.timeline.slider.set_package_markers([],[])
        self.window.editor.workflow.scheme_group.setEnabled(True)
        self.window.editor.workflow.scheme = self.previous_scheme
        self.window.annotation_panel.replace_labels([AnnotationLabel(**r) for r in self.previous_scheme['objects']['labels']])
        with QSignalBlocker(self.window.editor.workflow.scheme_selector):
            self.window.editor.workflow.scheme_selector.clear()
            self.window.editor.workflow.scheme_selector.addItem(self.previous_scheme['display_name'][current_language()],self.previous_scheme)
        self.window.editor.workflow.configure_display()
        self.window.editor.workflow._build_states()
        self.refresh()

    def _select_cine(self):
        if self.active and self.cines.currentData() != self.cine_id:
            self.switch_cine(self.cines.currentData())

    def switch_cine(self, cine):
        editor = self.window.editor
        editor.workflow.flush_notes()
        editor.cancel()
        self.cine_id = cine
        doc = self.package.documents[cine]
        editor.ready = False
        editor.document, editor.path, editor.selected_id = doc,None,None
        editor.undo_stack.clear()
        editor.workflow.scheme = deepcopy(self.package.scheme)
        self.window.annotation_panel.replace_labels([AnnotationLabel(**r) for r in self.package.scheme['objects']['labels']])
        with QSignalBlocker(editor.workflow.scheme_selector):
            editor.workflow.scheme_selector.clear()
            editor.workflow.scheme_selector.addItem(self.package.scheme['display_name'][current_language()],self.package.scheme)
        editor.workflow.configure_display()
        editor.workflow._build_states()
        editor.workflow.scheme_group.setEnabled(False)
        self.window.metadata = CineMetadata(filename=doc.cine_filename,file_size_bytes=doc.cine_file_size,
                                             frame_count=doc.frame_count,width=doc.width,height=doc.height,pixel_dtype='uint8')
        self.window.metadata_panel.set_metadata(self.window.metadata,TimingSummary())
        self.controller.state.frame_count = doc.frame_count
        photo = self.package.manifest['photometric'].get(cine)
        self.controller.photometric = PhotometricReference(**photo) if photo else None
        self.controller.photometric_error = None if photo else 'No exported reference gain'
        self.window.session = ViewerSession(doc.cine_filename,doc.cine_file_size,doc.frame_count)
        self.window.timeline.set_count(doc.frame_count)
        self.window.transport.setEnabled(True)
        self.window.display_panel.show_photometric() if photo else self.window.display_panel.show_raw()
        self.window._photometric_changed()
        self.window.display_panel.recalculate_button.setEnabled(False)
        targets = self.provider.available(cine,True)
        self.window.navigate((targets or self.provider.available(cine))[0])
        editor.changed()
        self.refresh()

    def adjacent(self, direction, targets=False):
        if self.active:
            index = self.provider.adjacent(self.cine_id,self.controller.state.frame_index,direction,targets)
            if index is not None:
                self.window.navigate(index)
            else:
                self.window.pause()

    def prepare_record(self, record):
        if self.active:
            self.begin_edit()
            self.package.mark_in_review()
            record.attributes.update(self.package.provenance())
            record.reviewer = self.package.provenance()['reviewer']
            record.source = 'manual'
        return record

    def record_state_provenance(self, record):
        if self.active:
            self.begin_edit()
            self.package.mark_in_review()
            self.package.review['record_provenance'][record.record_id] = self.package.provenance()
            return replace(record,review_status='edited' if record.derived_from else 'unreviewed')
        return record

    def decide(self, kind, status):
        if not self.active:
            return
        editor = self.window.editor
        editor.workflow.flush_notes()
        record = editor.selected_record() if kind == 'object' else editor.document.frame_state(self.controller.state.frame_index)
        if record is None:
            return
        self.begin_edit()
        key = record.annotation_id if kind == 'object' else record.record_id
        editor.undo_stack.push(DecisionCommand(self,kind,key,status))

    def note(self):
        if self.active:
            key = self.cine_id + ':' + str(self.controller.state.frame_index)
            value, ok = QInputDialog.getMultiLineText(self.window,tr('Review note...'),tr('Notes'),self.package.review['frame_notes'].get(key,''))
            if ok:
                self.begin_edit()
                self.package.mark_in_review()
                self.package.review['frame_notes'][key] = value
                self.refresh()

    def mark_frame(self):
        if self.active:
            key = [self.cine_id,self.controller.state.frame_index]
            if key not in self.package.review['reviewed_frames']:
                self.begin_edit()
                self.package.review['reviewed_frames'].append(key)
            self.refresh()

    def complete(self):
        if self.active and QMessageBox.question(self.window,tr('Complete review'),tr('Explicitly mark this package reviewed?')) == QMessageBox.StandardButton.Yes:
            self.begin_edit()
            self.package.manifest['package_status'] = 'reviewed'
            self.package.review['review_completed_at'] = _now()
            self.completed_revisions = {k:d._revision for k,d in self.package.documents.items()}
            self.completed_work = self.package.work_fingerprint()
            self.completion_time = self.package.review['review_completed_at']
            self.refresh()

    def document_changed(self):
        if self.active and self.completed_work is not None:
            if self.package.work_fingerprint() == self.completed_work:
                self.package.manifest['package_status'] = 'reviewed'
                if self.completion_time is not None:
                    self.package.review['review_completed_at'] = self.completion_time
            else:
                self.package.mark_in_review()
        if self.active:
            self.refresh()

    def save_dialog(self, checked=False):
        if not self.active:
            return False
        self.window.editor.workflow.flush_notes()
        name = (self.package.path.stem if self.package.path else 'review') + '_annotated.dvapkg'
        path, _ = QFileDialog.getSaveFileName(self.window,tr('Save Annotation Package As...'),str(self.output_path(name)),'Droplet Vision Annotation Package (*.dvapkg *.dvrpkg)')
        if not path:
            return False
        try:
            self.package.save(path)
            self.refresh()
            return True
        except Exception as error:
            self.window._error(str(error))
            return False

    def quick_save(self, checked=False):
        if not self.active:
            return False
        path = self.package.path
        if path is None or path.is_dir() or path.suffix.lower() != '.dvapkg':
            return self.save_dialog()
        self.window.editor.workflow.flush_notes()
        try:
            mode = path.stat().st_mode
            if not mode & stat.S_IWRITE or not os.access(path, os.W_OK):
                self.window._error(tr('This annotation package is read-only. Use Save Annotation Package As...'))
                self.refresh()
                return False
            self.package.save(path)
        except Exception as error:
            self.window._error(tr('Annotation package save failed; the original file was not overwritten.') + '\n'
                               + tr('Use Save Annotation Package As... to save to another location.') + '\n' + str(error))
            self.refresh()
            return False
        self.refresh()
        return True

    def confirm_discard(self):
        self.window.editor.workflow.flush_notes()
        if not self.active or not self.package.dirty:
            return True
        answer = QMessageBox.warning(self.window,tr('Unsaved annotation package'),tr('Save annotation package changes before continuing?'),
            QMessageBox.StandardButton.Save | QMessageBox.StandardButton.Discard | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Cancel)
        return self.save_dialog() if answer == QMessageBox.StandardButton.Save else answer == QMessageBox.StandardButton.Discard

    def autosave(self):
        if self.active and self.package.dirty:
            self.window.editor.workflow.flush_notes()
            self.package.save(output_path('annotation_packages/temp') / (self.package.manifest['package_id']+'.autosave.dvapkg'),mark_saved=False)

    def export_requests(self, selection, statuses):
        w, editor = self.window,self.window.editor
        editor.workflow.flush_notes()
        if selection != 'queue':
            if not editor.ready or editor.document is None or w.cine_path is None:
                raise ValueError(tr('Open a Cine and annotation document first.'))
            from .widgets.annotation_markers import human_frames
            targets = [w.current_record.frame_index] if selection == 'current' else sorted(human_frames(editor.document,w.layers))
            return [{'path':w.cine_path,'document':AnnotationDocument.from_dict(editor.document.to_dict()),'targets':targets,
                     'photometric':w.controller.photometric.to_dict() if w.controller.photometric else None}]
        queue = w.queue_manager
        if queue.queue is None or queue.root is None:
            raise ValueError(tr('Open a queue and set its local dataset root first.'))
        requests = {}
        for item in queue.queue.items:
            if item.status not in statuses:
                continue
            if item.relative_cine_path not in requests:
                cine = resolve_relative(queue.root,item.relative_cine_path)
                if w.cine_path is not None and cine == w.cine_path.resolve() and editor.document is not None:
                    doc = AnnotationDocument.from_dict(editor.document.to_dict())
                elif item.annotation_document:
                    doc = AnnotationDocument.load(resolve_relative(queue.path.parent,item.annotation_document))
                else:
                    raise ValueError(tr('Selected queue items require a saved annotation document: ') + item.cine_filename)
                requests[item.relative_cine_path] = {'path':cine,'document':doc,'targets':[],'queue_item_ids':{}}
            request = requests[item.relative_cine_path]
            request['targets'].append(item.frame_index)
            request['queue_item_ids'].setdefault(item.frame_index,[]).append(item.item_id)
        return list(requests.values())

    def export_dialog(self):
        if self.active or self.task is not None:
            return
        dialog = ExportReviewDialog(self.window)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        folder = dialog.folder.isChecked()
        destination, _ = QFileDialog.getSaveFileName(self.window,tr('Create Annotation Package from Current Annotations...'),
            str(self.output_path('annotation_package' + ('' if folder else '.dvapkg'))),
            'Folder name (*)' if folder else 'Droplet Vision Annotation Package (*.dvapkg *.dvrpkg)')
        if not destination:
            return
        try:
            requests = self.export_requests(dialog.selection.currentData(),[s for s,b in dialog.statuses.items() if b.isChecked()])
            scheme = deepcopy(self.window.editor.workflow.scheme)
            for request in requests:
                if request['document'].scheme and request['document'].scheme != scheme:
                    raise ValueError('Selected documents use different scheme snapshots; export them separately')
                if Path(request['path']).resolve().parent in Path(destination).resolve().parents:
                    raise ValueError('Do not export into the source Cine directory')
            context, creator, purpose = dialog.context.value(), dialog.creator.text(), dialog.purpose.currentData()
            version = project_metadata()[0]
            def work():
                result = export_cines(requests,scheme,context,creator,version,purpose)
                result.save(destination,folder=folder)
                return result
            self.progress = QProgressDialog(tr('Exporting raw annotation frames...'),'',0,0,self.window)
            self.progress.setCancelButton(None)
            self.progress.show()
            self.task = _Task(0,'review_export',work)
            self.task.signals.done.connect(self._export_done)
            self.pool.start(self.task)
        except Exception as error:
            self.window._error(str(error))

    def batch_dialog(self):
        from .batch_package import BatchPackageDialog
        if self.batch_window is None or not self.batch_window.isVisible():
            if self.batch_window is not None:
                self.batch_window.deleteLater()
            self.batch_window = BatchPackageDialog(self.window.editor.workflow.scheme, self.window, project_metadata()[0])
        self.batch_window.show()
        self.batch_window.raise_()

    def uniform_dialog(self):
        if self.task is not None:
            return
        from .uniform_package import UniformPackageDialog
        from ..review_package.cine_export import export_uniform_cine
        dialog = UniformPackageDialog(self.window, self.window.cine_path)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        name = Path(dialog.path.text()).stem + f'_uniform_{dialog.samples.value()}.dvapkg'
        destination, _ = QFileDialog.getSaveFileName(self.window,
            tr('Create Annotation Package from Uniform Cine Sampling...'), str(self.output_path(name)),
            'Droplet Vision Annotation Package (*.dvapkg)')
        if not destination:
            return
        scheme = deepcopy(self.window.editor.workflow.scheme)
        self.window.editor.workflow.flush_notes()
        document = None
        if (not self.active and self.window.cine_path is not None
                and Path(dialog.path.text()).resolve() == self.window.cine_path.resolve()
                and self.window.editor.document is not None):
            document = AnnotationDocument.from_dict(self.window.editor.document.to_dict())
        # Snapshot UI values before dispatch; worker never reads Qt widgets.
        path, count, expected = dialog.path.text(), dialog.samples.value(), deepcopy(dialog.info)
        options = dict(context=dialog.context.value(), purpose=dialog.purpose.currentData(),
                       creator=dialog.creator.text(), version=project_metadata()[0],
                       allow_short=dialog.allow_short, expected=expected, document=document)
        self.progress = QProgressDialog(tr('Exporting raw annotation frames...'), '', 0, 0, self.window)
        self.progress.setCancelButton(None)
        self.progress.show()
        self.task = _Task(0, 'uniform_export', lambda: export_uniform_cine(path, destination, count, scheme, **options))
        self.task.signals.done.connect(self._export_done)
        self.pool.start(self.task)
        self.refresh()

    @staticmethod
    def output_path(name):
        directory = output_path('annotation_packages/exported').resolve()
        directory.mkdir(parents=True, exist_ok=True)
        return directory / name

    def _export_done(self, token, kind, result, error):
        self.progress.close()
        self.task = None
        self.refresh()
        if error:
            self.window._error(error)
        else:
            size = sum(p.stat().st_size for p in result.path.rglob('*') if p.is_file()) if result.path.is_dir() else result.path.stat().st_size
            QMessageBox.information(self.window,tr('Annotation Package'),json.dumps({**result.summary(),'bytes':size},indent=2))

    def import_dialog(self):
        editor = self.window.editor
        if self.active or editor.document is None:
            return
        path, _ = QFileDialog.getOpenFileName(self.window,tr('Import Returned Annotation Package...'),str(output_path('annotation_packages')),'Droplet Vision Annotation Package (*.dvapkg *.dvrpkg)')
        if not path:
            return
        try:
            editor.workflow.flush_notes()
            package = ReviewPackage.open(path)
            merged, conflicts = merge_review(editor.document,package)
            if conflicts:
                dialog = ConflictDialog(conflicts,self.window)
                if dialog.exec() != QDialog.DialogCode.Accepted:
                    return
                merged, _ = merge_review(editor.document,package,{k:c.currentData() for k,c in dialog.choices.items()})
            editor.cancel()
            editor.document = merged
            editor.undo_stack.clear()
            editor.changed()
            self.window.statusBar().showMessage(tr('Imported Reviewed candidates. Manual records unchanged. Save annotations to persist.'))
        except Exception as error:
            self.window._error(str(error))
