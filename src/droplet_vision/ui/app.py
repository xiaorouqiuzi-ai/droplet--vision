"""Viewer application entry point."""
from __future__ import annotations
from .i18n import tr
import argparse
from pathlib import Path
from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import QApplication
from .main_window import MainWindow


def open_startup_file(window, path):
    """Shared file-association entry; package opening never requires a Cine."""
    try:
        suffix = Path(path).suffix.lower()
        if suffix == '.cine':
            window.open_cine(path)
        elif suffix in ('.dvapkg', '.dvrpkg'):
            from ..review_package import ReviewPackage
            package = ReviewPackage.open(path)
            window.review_manager.open(package, package.review.get('reviewer', {}).get('display_name', ''))
        else:
            window._error(tr('Open a .cine, .dvapkg or .dvrpkg file.'))
    except Exception as error:
        window._error(str(error))


def main(argv=None):
    parser = argparse.ArgumentParser(description=tr("Droplet Annotation Workstation — Annotation Editor v1"))
    inputs = parser.add_mutually_exclusive_group()
    inputs.add_argument("file", nargs="?", help="Cine or Annotation Package to open")
    inputs.add_argument("--cine", help="Legacy source-launcher file option")
    parser.add_argument("--taxonomy", help="Alternative taxonomy JSON")
    args = parser.parse_args(argv)
    QApplication.setAttribute(Qt.ApplicationAttribute.AA_DontUseNativeDialogs)
    app = QApplication.instance() or QApplication([])
    window = MainWindow(taxonomy_path=args.taxonomy)
    window.show()
    path = args.file or args.cine
    if path:
        QTimer.singleShot(0, lambda: open_startup_file(window, path))
    return app.exec()
