"""Local-only document location, never serialized into annotation data."""
from pathlib import Path
from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QGroupBox, QFormLayout, QLabel, QPushButton, QHBoxLayout, QApplication
from ..i18n import tr
from ..widgets.wrapped_label import WrappedLabel
from PySide6.QtWidgets import QVBoxLayout


class AnnotationDataPanel(QGroupBox):
    def __init__(self, parent=None):
        super().__init__(tr('Current Annotation Data'), parent)
        form = QFormLayout(self)
        form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapAllRows)
        self.filename, self.location, self.status = WrappedLabel(), WrappedLabel(), WrappedLabel()
        self.filename.setProperty('literal_text', True)
        self.location.setProperty('literal_text', True)
        self.location_caption = QLabel(tr('Location'))
        for label in (self.filename, self.location, self.status):
            label.setTextFormat(Qt.TextFormat.PlainText)
            label.setWordWrap(True)
            label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            label.setMinimumWidth(0)
        form.addRow(tr('File'), self.filename)
        form.addRow(self.location_caption, self.location)
        form.addRow(tr('Status'), self.status)
        row = QVBoxLayout()
        self.copy_button = QPushButton(tr('Copy Path'))
        self.folder_button = QPushButton(tr('Open Folder'))
        row.addWidget(self.copy_button)
        row.addWidget(self.folder_button)
        form.addRow(row)
        self.copy_button.clicked.connect(self.copy_path)
        self.folder_button.clicked.connect(self.open_folder)
        self.local_path = None
        self.update_document(None, None, None)

    def update_document(self, document, path, proposed, notes_pending=False):
        self.local_path = Path(path or proposed).resolve() if (path or proposed) else None
        actual = path is not None
        self.filename.setText(Path(path).name if actual else tr('Not saved yet'))
        self.location_caption.setText(tr('Location' if actual else 'Suggested location'))
        self.location.setText(str(self.local_path) if self.local_path else '—')
        dirty = document is not None and (document.dirty or notes_pending)
        self.status.setText(tr('Unsaved changes' if dirty else ('Saved' if actual else 'Not saved yet')))
        self.copy_button.setEnabled(self.local_path is not None)
        self.copy_button.setToolTip(tr('Copy actual annotation path' if actual else 'Copy suggested path; no file has been saved yet.'))
        self.folder_button.setEnabled(self.local_path is not None)

    def copy_path(self):
        if self.local_path is not None:
            QApplication.clipboard().setText(str(self.local_path))

    def open_folder(self):
        if self.local_path is not None:
            # For a proposed directory that does not exist yet, open the closest
            # existing parent without creating any folder as a side effect.
            folder = self.local_path.parent
            while not folder.exists() and folder != folder.parent:
                folder = folder.parent
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(folder)))
