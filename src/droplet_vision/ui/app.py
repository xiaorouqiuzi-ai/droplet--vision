"""Viewer application entry point."""
from __future__ import annotations
import argparse
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication
from .main_window import MainWindow


def main(argv=None):
    parser = argparse.ArgumentParser(description="Droplet Annotation Workstation — Cine Viewer v1")
    parser.add_argument("--cine")
    parser.add_argument("--taxonomy", help="Alternative taxonomy JSON")
    args = parser.parse_args(argv)
    QApplication.setAttribute(Qt.ApplicationAttribute.AA_DontUseNativeDialogs)
    app = QApplication.instance() or QApplication([])
    window = MainWindow(taxonomy_path=args.taxonomy)
    window.show()
    if args.cine:
        window.open_cine(args.cine)
    return app.exec()
