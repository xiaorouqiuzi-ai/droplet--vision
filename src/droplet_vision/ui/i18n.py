"""Central UI catalog. Stable IDs/data never pass through this layer.

Language preferences use local QSettings; switching is persisted immediately,
with a restart notice so partially edited documents are never rebuilt/discarded.
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
