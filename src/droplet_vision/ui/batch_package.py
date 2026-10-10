"""Nonblocking recursive batch dialog; all filesystem work runs off the UI thread."""
from copy import deepcopy
from threading import Event

from PySide6.QtCore import QObject, Signal, QThreadPool, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QFormLayout,
    QLabel, QLineEdit, QPushButton, QSpinBox, QComboBox, QFileDialog, QTableWidget,
    QTableWidgetItem, QHeaderView, QProgressBar, QMessageBox)

from ..review_package.batch import scan_batch, execute_batch, BatchCancelled
from .cine_controller import _Task
from .i18n import tr, current_language


class _Progress(QObject):
    changed = Signal(object)


class BatchPackageDialog(QDialog):
    def __init__(self, scheme, parent=None, version='unknown'):
        super().__init__(parent)
        self.scheme, self.version = deepcopy(scheme), version
        self.plan = self.result_data = self.task = None
        self.cancel_event = Event()
        self.pool = QThreadPool(self)
        self.pool.setMaxThreadCount(1)
        self.events = _Progress(self)
        self.events.changed.connect(self.on_progress)
        self.last_progress = None
        self.resize(900, 650)
        layout = QVBoxLayout(self)
        form = QFormLayout()
        layout.addLayout(form)
        self.labels = {}
        self.inputs = []
        for attr, title in [('source', 'Source folder'), ('output', 'Output parent folder')]:
            row = QHBoxLayout()
            edit = QLineEdit()
            setattr(self, attr, edit)
            button = QPushButton(tr('Browse...'))
            button.clicked.connect(lambda checked=False, target=edit, key=title: self.choose(target, key))
            row.addWidget(edit, 1)
            row.addWidget(button)
            label = QLabel()
            self.labels[title] = label
            form.addRow(label, row)
            self.inputs.extend([edit, button])
            edit.textChanged.connect(self.invalidate)
        self.samples = QSpinBox()
        self.samples.setRange(2, 10000)
        self.samples.setValue(20)
        self.context = QSpinBox()
        self.context.setRange(0, 100)
        self.policy = QComboBox()
        for key in ('skip', 'overwrite', 'report_conflict'):
            self.policy.addItem('', key)
        for key, widget in [('Samples per Cine', self.samples), ('Context frames before / after', self.context),
                            ('Existing packages', self.policy)]:
            self.labels[key] = QLabel()
            form.addRow(self.labels[key], widget)
            self.inputs.append(widget)
        self.samples.valueChanged.connect(self.invalidate)
        self.context.valueChanged.connect(self.invalidate)
        self.policy.currentIndexChanged.connect(self.invalidate)
        self.scheme_label, self.hint, self.summary, self.current = (QLabel() for _ in range(4))
        for label in (self.scheme_label, self.hint, self.summary, self.current):
            label.setWordWrap(True)
            layout.addWidget(label)
        self.table = QTableWidget(0, 5)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setStretchLastSection(True)
        layout.addWidget(self.table, 1)
        self.overall = QProgressBar()
        self.frames = QProgressBar()
        layout.addWidget(self.overall)
        layout.addWidget(self.frames)
        row = QHBoxLayout()
        layout.addLayout(row)
        self.scan_button, self.start_button, self.cancel_button = (QPushButton() for _ in range(3))
        self.open_output, self.failures_button = QPushButton(), QPushButton()
        for button in (self.scan_button, self.start_button, self.cancel_button, self.open_output, self.failures_button):
            row.addWidget(button)
        self.scan_button.clicked.connect(self.scan)
        self.start_button.clicked.connect(self.start)
        self.cancel_button.clicked.connect(self.cancel)
        self.open_output.clicked.connect(self.open_folder)
        self.failures_button.clicked.connect(self.show_failures)
        self.open_output.setEnabled(False)
        self.failures_button.setEnabled(False)
        self.start_button.setEnabled(False)
        self.retranslate()

    @property
    def busy(self):
        return self.task is not None

    def choose(self, edit, title):
        path = QFileDialog.getExistingDirectory(self, tr(title), edit.text())
        if path:
            edit.setText(path)

    def invalidate(self, *args):
        if not self.busy:
            self.plan = self.result_data = None
            self.table.setRowCount(0)
            self.start_button.setEnabled(False)
            self.open_output.setEnabled(False)
            self.failures_button.setEnabled(False)
            self.summary.clear()

    def checkpoint(self):
        if self.cancel_event.is_set():
            raise BatchCancelled('Cancelled')

    def dispatch(self, kind, work):
        self.cancel_event.clear()
        self.cancel_button.setText(tr('Cancel'))
        self.last_progress = None
        self.task = _Task(0, kind, work)
        self.task.signals.done.connect(self.finished_work)
        for widget in self.inputs + [self.scan_button, self.start_button]:
            widget.setEnabled(False)
        self.overall.setRange(0, 0)
        self.frames.setValue(0)
        self.task.setAutoDelete(True)
        self.pool.start(self.task)

    def scan(self):
        if self.busy:
            return
        if not self.source.text().strip() or not self.output.text().strip():
            QMessageBox.warning(self, tr('Warning'), tr('Choose source and output folders first.'))
            return
        source, output, count = self.source.text(), self.output.text(), self.samples.value()
        context, policy = self.context.value(), self.policy.currentData()
        self.plan = self.result_data = None
        self.open_output.setEnabled(False)
        self.failures_button.setEnabled(False)
        self.dispatch('scan', lambda: scan_batch(source, output, count, self.scheme, context=context,
                      existing_policy=policy, checkpoint=self.checkpoint, progress=self.events.changed.emit))

    def start(self):
        if self.busy or self.plan is None:
            return
        plan = self.plan
        self.result_data = None
        self.dispatch('create', lambda: execute_batch(plan, checkpoint=self.checkpoint,
                      progress=self.events.changed.emit, version=self.version))

    def cancel(self):
        if self.busy:
            self.cancel_event.set()
            self.current.setText(tr('Cancelling after the current read; completed packages are retained.'))
        else:
            self.reject()

    def on_progress(self, event):
        self.last_progress = event
        self.overall.setRange(0, max(1, event['total']))
        self.overall.setValue(event['index'])
        if event['phase'] == 'create':
            self.frames.setRange(0, event['frame_total'])
            self.frames.setValue(event['decoded'])
            self.current.setText(tr('Reading Raw frame: {source} | {decoded}/{total} reads (including Ref90 reference)').format(
                source=event['source'], decoded=event['decoded'], total=event['frame_total']))
        else:
            self.current.setText(tr('Cine: {source} | {index}/{total}').format(**event))

    def finished_work(self, token, kind, result, error):
        self.task = None
        for widget in self.inputs + [self.scan_button]:
            widget.setEnabled(True)
        self.overall.setRange(0, 1)
        self.overall.setValue(1)
        if error:
            self.current.setText(tr('Cancelled') if self.cancel_event.is_set() else tr('Error') + ': ' + tr(error))
            if not self.cancel_event.is_set():
                QMessageBox.warning(self, tr('Error'), tr(error))
        elif kind == 'scan':
            self.plan = result
        else:
            self.result_data = result
            self.current.setText(tr('Cancelled' if result.cancelled else 'Batch annotation packages completed'))
        self.cancel_button.setText(tr('Close'))
        self.start_button.setEnabled(self.plan is not None and any(i.status != 'FAILED' for i in self.plan.items))
        self.open_output.setEnabled(self.result_data is not None)
        self.failures_button.setEnabled(bool(self.plan and any(i.status == 'FAILED' for i in self.items())))
        self.update_table()
        self.update_summary()

    def items(self):
        return self.result_data.items if self.result_data else self.plan.items if self.plan else []

    def update_table(self):
        items = self.items()
        self.table.setRowCount(len(items))
        for row, item in enumerate(items):
            values = [tr(item.status), item.relative_source_path, str(item.info['frame_count']) if item.info else '—',
                      str(item.actual_sample_count), item.relative_package_path]
            for col, value in enumerate(values):
                cell = QTableWidgetItem(value)
                cell.setToolTip(item.error_type + ': ' + item.error_message if item.error_type else value)
                self.table.setItem(row, col, cell)

    def update_summary(self):
        if self.result_data:
            r = self.result_data
            self.summary.setText(tr('Discovered: {total} | Created: {created} | Skipped / conflicts: {skipped} | Failed: {failed}\nOutput: {output}').format(
                total=len(r.items), created=r.created, skipped=r.skipped, failed=r.failed, output=self.plan.output_root))
        elif self.plan:
            items = self.plan.items
            exists = sum(i.status == 'EXISTS' for i in items)
            ready = sum(i.status != 'FAILED' for i in items)
            self.summary.setText(tr('Source: {source} | Cine files: {total} | Samples: {samples}\nExisting: {exists} | To create: {create} | Short Cine: {short}').format(
                source=self.plan.source_root.name, total=len(items), samples=self.plan.sample_count, exists=exists,
                create=ready if self.plan.existing_policy == 'overwrite' else ready-exists,
                short=sum(bool(i.info and i.info['frame_count'] < self.plan.sample_count) for i in items)))

    def retranslate(self):
        self.setWindowTitle(tr('Batch Annotation Packages from Folder'))
        for key, label in self.labels.items():
            label.setText(tr(key))
        for index, key in enumerate(('Skip existing', 'Overwrite existing', 'Report conflicts only')):
            self.policy.setItemText(index, tr(key))
        self.scheme_label.setText(tr('Annotation Scheme') + ': ' + self.scheme['display_name'][current_language()])
        self.hint.setText(tr('Short Cine files export all available frames. Sources remain read-only; output must be outside the source tree.'))
        for button, key in [(self.scan_button, 'Scan'), (self.start_button, 'Start creating'),
                            (self.cancel_button, 'Cancel' if self.busy or self.result_data is None else 'Close'), (self.open_output, 'Open output folder'),
                            (self.failures_button, 'View failures')]:
            button.setText(tr(key))
        self.table.setHorizontalHeaderLabels([tr(k) for k in ('Status', 'Relative path', 'Total frames', 'Target frames', 'Output path')])
        self.update_table()
        self.update_summary()
        if self.last_progress and self.busy:
            self.on_progress(self.last_progress)

    def open_folder(self):
        if self.plan:
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.plan.output_root)))

    def show_failures(self):
        QMessageBox.information(self, tr('Failed'), '\n'.join(
            f'{i.relative_source_path}: {i.error_type}: {i.error_message}' for i in self.items() if i.status == 'FAILED'))

    def done(self, result):
        if self.busy:
            self.cancel()
            return
        super().done(result)

    def closeEvent(self, event):
        if self.busy:
            self.cancel()
            event.ignore()
        else:
            super().closeEvent(event)
