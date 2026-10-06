"""Application branding, separate from scientific data and annotation schemes."""
from pathlib import Path
from importlib.metadata import metadata, PackageNotFoundError
from PySide6.QtCore import Qt
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QDialog, QVBoxLayout, QLabel, QDialogButtonBox
from .i18n import tr

REPOSITORY = 'https://github.com/xiaorouqiuzi-ai/droplet--vision'
ICON_DIRECTORY = Path(__file__).parent / 'assets/icons'


def app_icon():
    return QIcon(str(ICON_DIRECTORY / 'planico.ico'))


def project_metadata():
    try:
        project = metadata('droplet-vision')
        return project.get('Version', 'unknown'), project.get('Author') or 'xiaorouqiuzi-ai'
    except PackageNotFoundError:
        # Source-tree launcher does not require installing the package.
        try:
            import tomllib
            project = tomllib.loads((Path(__file__).resolve().parents[3] / 'pyproject.toml').read_text(encoding='utf-8'))['project']
            authors = [a['name'] for a in project.get('authors', []) if a.get('name')]
            return project.get('version', 'unknown'), ', '.join(authors) or 'xiaorouqiuzi-ai'
        except (ImportError, OSError, ValueError, KeyError):
            return 'unknown', 'xiaorouqiuzi-ai'


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
        self.description.setText(tr('Droplet Annotation Workstation') + '\n' +
            tr('Version: {version}').format(version=version) + '\n' +
            tr('Author / repository owner: {author}').format(author=author) + '\n\n' +
            tr('Cine review and manual annotation for suspended-droplet experiments.') + '\n' +
            tr('Raw scientific pixels, display preprocessing and annotation data remain separate.') + '\n\n' +
            tr('Application icon derived from the project planico.jpg.'))
