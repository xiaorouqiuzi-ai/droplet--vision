"""Metadata-only asynchronous preview for a single Cine annotation task."""
from pathlib import Path
from PySide6.QtCore import QThreadPool
from PySide6.QtWidgets import (QDialog, QFormLayout, QLineEdit, QPushButton,
    QSpinBox, QComboBox, QLabel, QDialogButtonBox, QFileDialog, QMessageBox)
from ..review_package.cine_export import inspect_cine
from ..sampling.uniform import uniform_frame_indices
from .cine_controller import _Task
from .i18n import tr


class UniformPackageDialog(QDialog):
    def __init__(self, parent=None, path=None):
        super().__init__(parent)
        self.setWindowTitle(tr('Create Annotation Package from Uniform Cine Sampling...'))
        self.info = None
        self.allow_short = False
        self.task = None
        self.pool = QThreadPool(self)
        self.pool.setMaxThreadCount(1)
        form = QFormLayout(self)
        self.path = QLineEdit()
        self.path.setReadOnly(True)
        form.addRow(tr('Cine file'), self.path)
        self.browse = QPushButton(tr('Browse...'))
        self.browse.clicked.connect(self.choose)
        form.addRow(self.browse)
        self.samples = QSpinBox()
        self.samples.setRange(2, 10000)
        self.samples.setValue(50)
        self.samples.valueChanged.connect(self.preview)
        form.addRow(tr('Requested samples'), self.samples)
        self.context = QSpinBox()
        self.context.setRange(0, 100)
        form.addRow(tr('Context frames before / after'), self.context)
        self.purpose = QComboBox()
        for title, key in [('New annotation task', 'annotation'), ('Review task', 'review'), ('General', 'general')]:
            self.purpose.addItem(tr(title), key)
        form.addRow(tr('Purpose'), self.purpose)
        self.creator = QLineEdit()
        form.addRow(tr('Creator (optional alias)'), self.creator)
        self.summary = QLabel()
        self.summary.setWordWrap(True)
        form.addRow(self.summary)
        hint = QLabel(tr('Uniform sampling creates annotation tasks; it does not identify physical events.'))
        hint.setWordWrap(True)
        form.addRow(hint)
        self.buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        self.buttons.accepted.connect(self.accept_checked)
        self.buttons.rejected.connect(self.reject)
        form.addRow(self.buttons)
        self.preview()
        if path:
            self.load_path(path)

    def choose(self):
        path, _ = QFileDialog.getOpenFileName(self, tr('Open Cine'), '', 'Phantom Cine (*.cine)')
        if path:
            self.load_path(path)

    def load_path(self, path):
        if self.task is not None:
            return
        self.info = None
        self.path.setText(str(Path(path).resolve()))
        self.browse.setEnabled(False)
        self.preview()
        self.summary.setText(tr('Reading Cine metadata...'))
        self.task = _Task(0, 'uniform_metadata', lambda: inspect_cine(path))
        self.task.signals.done.connect(self.loaded)
        self.pool.start(self.task)

    def loaded(self, token, kind, info, error):
        self.task = None
        self.browse.setEnabled(True)
        self.info = info if not error else None
        self.preview()
        if error:
            self.summary.setText(tr('Error') + ': ' + error)

    def preview(self):
        self.buttons.button(QDialogButtonBox.StandardButton.Ok).setEnabled(self.info is not None)
        if self.info is None:
            return
        indices = uniform_frame_indices(self.info['frame_count'], self.samples.value())
        self.summary.setText(tr('Cine: {cine}\nTotal frames: {total}\nRequested: {requested}\nActual targets: {actual}\nFirst: {first}\nLast: {last}\nApprox interval: {interval:.2f} frames').format(
            cine=self.info['filename'], total=self.info['frame_count'], requested=self.samples.value(),
            actual=len(indices), first=indices[0], last=indices[-1],
            interval=(indices[-1]-indices[0])/max(1, len(indices)-1)))

    def accept_checked(self):
        if self.info is None:
            return
        self.allow_short = self.info['frame_count'] < self.samples.value()
        if self.allow_short and QMessageBox.question(self, tr('Confirm'),
                tr('This Cine has only {total} frames; {requested} unique samples are impossible. Export all {total} frames?').format(
                    total=self.info['frame_count'], requested=self.samples.value()),
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
                QMessageBox.StandardButton.Cancel) != QMessageBox.StandardButton.Yes:
            return
        self.accept()

    def done(self, result):
        # Keep QObject signal receivers alive while a metadata read is in flight.
        if self.task is not None:
            return
        super().done(result)
