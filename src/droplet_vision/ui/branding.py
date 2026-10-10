"""Application branding, separate from scientific data and annotation schemes."""
from pathlib import Path
from .._version import DISPLAY_VERSION
from ..resources import ui_resource_path
from PySide6.QtCore import Qt
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QDialog, QVBoxLayout, QLabel, QDialogButtonBox
from .i18n import tr

REPOSITORY = 'https://github.com/xiaorouqiuzi-ai/droplet--vision'
ICON_DIRECTORY = ui_resource_path('assets/icons')


def app_icon():
    return QIcon(str(ICON_DIRECTORY / 'planico.ico'))


def project_metadata():
    return DISPLAY_VERSION, 'xiaorouqiuzi-ai'


class AboutDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowIcon(app_icon())
        layout = QVBoxLayout(self)
        icon = QLabel()
        icon.setPixmap(app_icon().pixmap(96, 96))
        icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(icon)
        self.description = QLabel()
        self.description.setWordWrap(True)
        self.description.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(self.description)
        link = QLabel(f'<a href="{REPOSITORY}">{REPOSITORY}</a>')
        link.setOpenExternalLinks(True)
        link.setWordWrap(True)
        layout.addWidget(link)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.close)
        layout.addWidget(buttons)
        self.resize(440, 350)
        self.retranslate()

    def retranslate(self):
        self.setWindowTitle(tr('About'))
        version, author = project_metadata()
        self.description.setText('Droplet Vision' + '\n' +
            tr('Version: {version}').format(version='v' + version) + '\n' +
            tr('Author / repository owner: {author}').format(author=author) + '\n\n' +
            tr('Cine review and manual annotation for suspended-droplet experiments.') + '\n' +
            tr('Raw scientific pixels, display preprocessing and annotation data remain separate.') + '\n\n' +
            'License: BSD-3-Clause\n' + tr('Application icon derived from the project planico.jpg.'))
