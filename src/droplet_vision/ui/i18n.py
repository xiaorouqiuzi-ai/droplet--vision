"""Central UI catalog. Stable IDs/data never pass through this layer.

Language preferences use local QSettings; captions update in place without
rebuilding controls or touching user-entered text and annotation state.
English source phrases also serve as fallback keys. Composite diagnostic text
translates known phrases with word boundaries, leaving IDs/numbers intact.
"""
from __future__ import annotations
import json
import os
from pathlib import Path
import re
from PySide6.QtCore import QSettings, QTranslator
from PySide6.QtWidgets import QApplication

LANGUAGES = ('zh_CN', 'en_US')
_catalogs = {key: json.loads((Path(__file__).parent/'translations'/(key+'.json')).read_text(encoding='utf-8'))
             for key in LANGUAGES}
_pattern = re.compile(r'(?<![\w])(' + '|'.join(re.escape(k) for k in sorted(_catalogs['en_US'],key=len,reverse=True)) + r')(?![\w])')
_language = 'zh_CN'
_qt_translator = None


def preferences():
    return QSettings('DropletVision', 'AnnotationWorkstation')


def current_language():
    return _language


def preferred_language(store=None):
    value = (store or preferences()).value('ui/language', 'zh_CN')
    return value if value in LANGUAGES else 'zh_CN'


def save_language(language, store=None):
    if language not in LANGUAGES:
        raise ValueError('Unsupported language')
    settings = store or preferences()
    settings.setValue('ui/language', language)
    settings.sync()
    if settings.status() != QSettings.Status.NoError:
        raise OSError('Could not save language preference')


def set_language(language):
    global _language
    if language not in LANGUAGES:
        raise ValueError('Unsupported language')
    _language = language


def tr(text):
    text = str(text)
    catalog = _catalogs[_language]
    if text in catalog:
        return catalog[text]
    return _pattern.sub(lambda m: catalog.get(m[0], _catalogs['en_US'].get(m[0],m[0])), text)


class CatalogTranslator(QTranslator):
    def translate(self, context, sourceText, disambiguation=None, n=-1):
        # Standard Qt Save/Discard/Cancel buttons use mnemonic markers.
        source = sourceText.replace('&','')
        # None maps to a null QString: Qt falls back to the source text.
        # An empty string is a successful *blank* translation in PySide.
        return tr(source) if source in _catalogs['en_US'] else None


def initialize():
    global _qt_translator
    set_language(os.environ.get('DROPLET_VISION_LANGUAGE') or preferred_language())
    app = QApplication.instance()
    if app is not None and _qt_translator is None:
        _qt_translator = CatalogTranslator(app)
        app.installTranslator(_qt_translator)


def retranslate_tree(root, previous_language):
    """Refresh exact catalog captions in place, never editor values or item IDs.

    Dynamic/Scheme text is refreshed by its owning presenter afterwards. Exact
    matching avoids translating fragments of paths, user notes or stable IDs.
    All combo signals are blocked so changing a caption cannot select a tool.
    """
    from PySide6.QtCore import QObject, QSignalBlocker
    from PySide6.QtGui import QAction
    from PySide6.QtWidgets import (QLabel, QAbstractButton, QGroupBox, QMenu,
        QDockWidget, QComboBox, QLineEdit, QTextEdit)
    from .widgets.wrapped_label import WrappedLabel
    sources = {value: key for key, value in _catalogs[previous_language].items()}
    def translated(value):
        key = sources.get(value)
        return tr(key) if key is not None else value
    for obj in [root] + root.findChildren(QObject):
        if not isinstance(obj, (QLabel, QAbstractButton, QAction, WrappedLabel, QGroupBox,
                                QMenu, QDockWidget, QComboBox, QLineEdit, QTextEdit)):
            continue  # QTextDocument frames can be replaced when captions change.
        with QSignalBlocker(obj):
            if isinstance(obj, (QLabel, QAbstractButton, QAction, WrappedLabel)):
                if not obj.property('literal_text'):
                    obj.setText(translated(obj.text()))
            if isinstance(obj, (QGroupBox, QMenu)):
                obj.setTitle(translated(obj.title()))
            if isinstance(obj, QDockWidget):
                obj.setWindowTitle(translated(obj.windowTitle()))
            if isinstance(obj, QComboBox):
                for index in range(obj.count()):
                    obj.setItemText(index, translated(obj.itemText(index)))
            if isinstance(obj, (QLineEdit, QTextEdit)):
                obj.setPlaceholderText(translated(obj.placeholderText()))
            for name in ('toolTip', 'statusTip'):
                if hasattr(obj, name):
                    getattr(obj, 'set' + name[0].upper() + name[1:])(translated(getattr(obj, name)()))
