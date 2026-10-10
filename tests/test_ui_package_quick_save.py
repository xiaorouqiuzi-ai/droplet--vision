"""Current-file saves, effective-work clean state and atomic failure boundaries."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from copy import deepcopy
import json
from pathlib import Path
import stat
import sys
import tempfile
import unittest
from unittest.mock import patch
import zipfile
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'src'))
from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication, QMessageBox
from droplet_vision.ui import i18n
from droplet_vision.ui.main_window import MainWindow
from droplet_vision.review_package import AnnotationPackage
from test_review_package import fixture


class PackageQuickSaveTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        pref = patch.object(i18n, 'preferences', return_value=QSettings(str(self.root/'prefs.ini'), QSettings.Format.IniFormat))
        pref.start(); self.addCleanup(pref.stop)
        self.w = MainWindow()
        self.addCleanup(self.close)

    def close(self):
        with patch.object(QMessageBox, 'warning', return_value=QMessageBox.StandardButton.Discard):
            self.w.close()
        self.app.processEvents()

    def opened(self, suffix='.dvapkg', folder=False, reviewed=False):
        _, original, _, _, package = fixture()
        if reviewed:
            package.manifest['package_status'] = 'reviewed'
            package.review['review_completed_at'] = '2026-01-01T00:00:00+00:00'
        if suffix == '.dvrpkg':
            package.manifest['package_format_version'] = 1
            package.manifest.pop('package_kind'); package.manifest.pop('package_purpose')
        self.path = self.root/('folder' if folder else 'current'+suffix)
        package.save(self.path, folder=folder)
        self.package = AnnotationPackage.open(self.path)
        self.assertTrue(self.w.review_manager.open(self.package, 'Test annotator'))
        self.original = original
        return original

    def edit(self):
        self.assertTrue(self.w.editor.edit_annotation(self.original.annotation_id,
            {'points': [[4,4], [15,3], [15,15]]}))

    def test_normal_clean_and_display_only_hidden(self):
        button = self.w.transport.save_package
        self.assertTrue(button.isHidden())
        self.opened()
        original = self.package.fingerprint()
        self.assertFalse(self.package.dirty)
        self.assertTrue(button.isHidden())
        self.w.canvas.scale(2, 2)
        self.w.canvas.horizontalScrollBar().setValue(5)
        self.w.display_panel.show_raw(); self.w.display_panel.show_photometric()
        self.w.editor.set_record_visible(self.original.annotation_id, False)
        self.w.change_language('en_US'); self.w.change_language('zh_CN')
        self.w.review_manager.adjacent(1)
        self.assertEqual(original, self.package.fingerprint())
        self.assertFalse(self.package.dirty)
        self.assertTrue(button.isHidden())
        self.assertNotIn('*', self.w.windowTitle())

    def test_edit_undo_redo_and_same_path_atomic_save(self):
        self.opened()
        old = self.path.read_bytes()
        self.edit()
        record = self.w.editor.selected_record().to_dict()
        self.assertFalse(self.w.transport.save_package.isHidden())
        self.w.editor.undo()
        self.assertFalse(self.package.dirty)
        self.assertTrue(self.w.transport.save_package.isHidden())
        self.assertEqual(len(self.w.editor.document.records.records()), 2)  # History retained.
        self.w.editor.redo()
        self.assertTrue(self.package.dirty)
        self.assertFalse(self.w.transport.save_package.isHidden())
        before_save = deepcopy(self.package.documents['synthetic'].to_dict())
        raw = deepcopy(self.package.frames)
        metadata = deepcopy(self.package.manifest['frames'])
        photo = deepcopy(self.package.manifest['photometric'])
        with patch('droplet_vision.ui.review_package.QFileDialog.getSaveFileName', side_effect=AssertionError('No Save As')):
            self.w.transport.save_package.click()
        self.assertEqual(self.package.path, self.path)
        self.assertNotEqual(old, self.path.read_bytes())
        self.assertFalse(self.package.dirty)
        self.assertTrue(self.w.transport.save_package.isHidden())
        self.assertNotIn('*', self.w.windowTitle())
        self.assertEqual(self.package.documents['synthetic'].to_dict(), before_save)
        loaded = AnnotationPackage.open(self.path)
        self.assertEqual(loaded.documents['synthetic'].active_records(10)[0].to_dict(), record)
        self.assertEqual(loaded.frames, raw)
        self.assertEqual(loaded.manifest['frames'], metadata)
        self.assertEqual(loaded.manifest['photometric'], photo)
        self.assertEqual(loaded.scheme, self.package.scheme)
        from io import BytesIO
        with zipfile.ZipFile(BytesIO(old)) as z: old_hashes = json.loads(z.read('checksums/sha256.json'))
        with zipfile.ZipFile(self.path) as z: new_hashes = json.loads(z.read('checksums/sha256.json'))
        for name in raw: self.assertEqual(old_hashes[name], new_hashes[name])
        self.assertNotEqual(old_hashes, new_hashes)
        self.w.editor.undo(); self.assertTrue(self.package.dirty)
        self.w.editor.redo(); self.assertFalse(self.package.dirty)

    def test_state_uncertain_pending_notes_and_progress(self):
        self.opened()
        self.w.editor.workflow.checkboxes['bubble_growth'].setChecked(True)
        self.assertFalse(self.w.transport.save_package.isHidden())
        self.w.editor.undo(); self.assertFalse(self.package.dirty)
        self.w.editor.workflow.uncertain.setChecked(True)
        self.assertFalse(self.w.transport.save_package.isHidden())
        self.w.editor.undo(); self.assertFalse(self.package.dirty)
        self.w.editor.workflow.notes.setPlainText('new pending note')
        self.assertFalse(self.w.transport.save_package.isHidden())
        self.assertTrue(self.w.review_manager.dirty)
        self.assertTrue(self.w.review_manager.quick_save())
        loaded = AnnotationPackage.open(self.path)
        self.assertEqual(loaded.documents['synthetic'].frame_state(10).notes, 'new pending note')
        self.assertFalse(self.package.dirty)
        self.w.editor.workflow.notes.setPlainText('temporary')
        self.w.editor.workflow.notes.setPlainText('new pending note')
        self.assertTrue(self.w.transport.save_package.isHidden())
        self.w.review_manager.adjacent(1, True)
        self.w.review_manager.mark_frame()
        self.assertTrue(self.package.dirty)
        self.assertTrue(self.w.review_manager.quick_save())
        self.assertEqual(AnnotationPackage.open(self.path).progress('synthetic'), (2,2,0))

    def test_failures_leave_original_intact_and_dirty(self):
        self.opened(); self.edit()
        original = self.path.read_bytes()
        for target in ('replace', 'validate', 'checksum', 'write'):
            with self.subTest(target=target):
                if target == 'replace': mocked = patch('droplet_vision.review_package.bundle.os.replace', side_effect=OSError('locked'))
                elif target == 'validate': mocked = patch.object(AnnotationPackage, '_from_files', side_effect=ValueError('invalid'))
                elif target == 'checksum': mocked = patch.object(self.package, 'files', side_effect=ValueError('checksum'))
                else: mocked = patch('droplet_vision.review_package.bundle.zipfile.ZipFile.writestr', side_effect=OSError('disk full'))
                with mocked, patch.object(self.w, '_error') as error:
                    self.assertFalse(self.w.review_manager.quick_save())
                    self.assertTrue(error.called)
                self.assertEqual(original, self.path.read_bytes())
                self.assertTrue(self.package.dirty)
                self.assertFalse(self.w.transport.save_package.isHidden())
                AnnotationPackage.open(self.path)

    def test_readonly_suggests_save_as(self):
        self.opened(); self.edit()
        before = self.path.read_bytes()
        self.path.chmod(stat.S_IREAD)
        try:
            with patch.object(self.w, '_error') as error:
                self.assertFalse(self.w.review_manager.quick_save())
                self.assertIn(i18n.tr('This annotation package is read-only. Use Save Annotation Package As...'), error.call_args.args[0])
            self.assertFalse(self.w.transport.save_package.isHidden())
            self.assertEqual(before, self.path.read_bytes())
        finally:
            self.path.chmod(stat.S_IREAD | stat.S_IWRITE)

    def test_legacy_and_folder_route_to_new_file(self):
        for suffix, folder in [('.dvrpkg', False), ('.dvapkg', True)]:
            with self.subTest(folder=folder):
                self.opened(suffix, folder)
                before = self.path.read_bytes() if not folder else (self.path/'manifest.json').read_bytes()
                self.edit()
                self.assertEqual(self.w.transport.save_package.text(), i18n.tr('Save as New Annotation Package'))
                destination = self.root/('from_folder.dvapkg' if folder else 'upgraded.dvapkg')
                with patch('droplet_vision.ui.review_package.QFileDialog.getSaveFileName', return_value=(str(destination),'')) as dialog:
                    self.assertTrue(self.w.review_manager.quick_save())
                    self.assertTrue(dialog.call_args.args[2].endswith('.dvapkg'))
                self.assertEqual(before, self.path.read_bytes() if not folder else (self.path/'manifest.json').read_bytes())
                self.assertEqual(self.package.path, destination)
                self.assertTrue(self.w.transport.save_package.isHidden())
                self.w.review_manager.leave(); self.w._reset()

    def test_reviewed_snapshot_undo_restores_clean(self):
        self.opened(reviewed=True)
        self.assertFalse(self.package.dirty)
        self.edit(); self.assertTrue(self.package.dirty)
        self.w.editor.undo()
        self.assertFalse(self.package.dirty)
        self.assertEqual(self.package.manifest['package_status'], 'reviewed')
        self.assertTrue(self.w.transport.save_package.isHidden())
        self.w.editor.redo(); self.assertTrue(self.package.dirty)

    def test_reject_undo_and_language_button(self):
        self.opened()
        self.w.editor.select(self.original.annotation_id)
        self.w.review_manager.decide('object', 'rejected')
        self.assertTrue(self.package.dirty)
        self.w.editor.undo(); self.assertFalse(self.package.dirty)
        self.w.editor.redo(); self.assertTrue(self.package.dirty)
        self.w.change_language('en_US')
        self.assertEqual(self.w.transport.save_package.text(), 'Save Annotation Package')
        self.w.change_language('zh_CN')
        self.assertEqual(self.w.transport.save_package.text(), '保存标注包')

    def test_add_rename_review_note_and_return_to_normal_mode(self):
        self.opened()
        self.w.annotation_panel.select_label_id('parent_droplet')
        self.assertTrue(self.w.editor.create_annotation('polygon', {'points': [[2,2], [6,2], [6,6]]}))
        self.assertFalse(self.w.transport.save_package.isHidden())
        self.w.editor.undo()
        self.assertTrue(self.w.transport.save_package.isHidden())
        self.w.editor.select(self.original.annotation_id)
        self.assertTrue(self.w.editor.rename_selected('Renamed_01'))
        self.assertTrue(self.package.dirty)
        self.w.editor.undo(); self.assertFalse(self.package.dirty)
        with patch('droplet_vision.ui.review_package.QInputDialog.getMultiLineText', return_value=('Review note', True)):
            self.w.review_manager.note()
        self.assertFalse(self.w.transport.save_package.isHidden())
        self.assertTrue(self.w.review_manager.quick_save())
        self.assertEqual(AnnotationPackage.open(self.path).review['frame_notes']['synthetic:10'], 'Review note')
        self.assertTrue(self.w.close_cine())
        self.assertTrue(self.w.transport.save_package.isHidden())
