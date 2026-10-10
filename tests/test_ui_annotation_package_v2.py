import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from pathlib import Path
import tempfile
import sys
import unittest
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from PySide6.QtCore import QSettings, QPoint, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QMessageBox, QDialog, QDialogButtonBox
from droplet_vision.ui import i18n
from droplet_vision.ui.main_window import MainWindow
from droplet_vision.ui.uniform_package import UniformPackageDialog
from droplet_vision.review_package import AnnotationPackage, merge_review
from test_uniform_annotation_package import empty_package


class AnnotationPackageUITests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        settings = QSettings(str(Path(self.tmp.name)/'settings.ini'), QSettings.Format.IniFormat)
        pref = patch.object(i18n, 'preferences', return_value=settings)
        pref.start(); self.addCleanup(pref.stop)
        self.window = MainWindow()
        self.addCleanup(self.close_window)

    def close_window(self):
        with patch.object(QMessageBox, 'warning', return_value=QMessageBox.StandardButton.Discard):
            self.window.close()
        self.app.processEvents()

    def test_functions_actions_languages_no_file_utilities(self):
        for lang in ('zh_CN', 'en_US', 'zh_CN'):
            self.window.change_language(lang)
            self.assertEqual([a.text() for a in self.window.menuBar().actions()],
                [i18n.tr(k) for k in ('File', 'Annotation', 'Queue', 'View', 'Model', 'Settings', 'Functions', 'Help')])
            functions = [a.text() for a in self.window.functions_menu.actions()]
            for key in ('Create Annotation Package from Uniform Cine Sampling...',
                        'Create Annotation Package from Current Annotations...', 'Open Annotation Package...',
                        'Save Annotation Package As...', 'Import Returned Annotation Package...'):
                self.assertIn(i18n.tr(key), functions)
                self.assertNotIn(i18n.tr(key), [a.text() for a in self.window.file_menu.actions()])

    def test_dialog_preview_defaults_short_confirmation_and_cancel(self):
        d = UniformPackageDialog(self.window)
        self.assertEqual(d.samples.value(), 50)
        self.assertEqual(d.samples.minimum(), 2)
        self.assertEqual(d.context.value(), 0)
        self.assertEqual(d.purpose.currentData(), 'annotation')
        self.assertFalse(d.buttons.button(QDialogButtonBox.StandardButton.Ok).isEnabled())
        d.info = {'filename': 'sample.cine', 'frame_count': 32196}
        d.preview()
        self.assertIn('32195', d.summary.text())
        self.assertIn('657.04', d.summary.text())
        d.info['frame_count'] = 10
        with patch.object(QMessageBox, 'question', return_value=QMessageBox.StandardButton.Cancel):
            d.accept_checked()
        self.assertNotEqual(d.result(), QDialog.DialogCode.Accepted)
        with patch.object(QMessageBox, 'question', return_value=QMessageBox.StandardButton.Yes):
            d.accept_checked()
        self.assertEqual(d.result(), QDialog.DialogCode.Accepted)
        self.assertTrue(d.allow_short)

    def test_raw_only_package_annotate_save_reopen_merge_without_cine(self):
        local, _, package = empty_package()
        w = self.window; manager = w.review_manager
        with patch.object(manager.normal_controller, '_reader_factory', side_effect=AssertionError('Cine access')):
            self.assertTrue(manager.open(package, 'Annotator test'))
            self.assertEqual(package.progress(local.cine_id), (3, 0, 3))
            manager.adjacent(1, True)
            self.assertEqual(w.current_record.frame_index, 50)
            self.assertEqual(package.progress(local.cine_id), (3, 0, 3))  # Viewing is not completion.
            self.assertTrue(w.editor.create_annotation('polygon', {'points': [[1,1], [12,1], [12,12]]}))
            w.editor.workflow.checkboxes['burning'].setChecked(True)
            self.assertEqual(package.progress(local.cine_id), (3, 1, 2))
            path = Path(self.tmp.name)/'annotated.dvapkg'
            with patch('droplet_vision.ui.review_package.QFileDialog.getSaveFileName', return_value=(str(path), '')) as dialog:
                self.assertTrue(manager.save_dialog())
            self.assertTrue(dialog.call_args.args[2].endswith('_annotated.dvapkg'))
            returned = AnnotationPackage.open(path)
            self.assertTrue(manager.open(returned, 'Annotator test'))
            manager.adjacent(1, True)
            self.assertEqual(len(w.editor.document.active_records(50)), 1)
            self.assertEqual(w.editor.document.frame_state(50).state_ids, ('burning',))
            self.assertEqual(w.timeline.slider.target_frames, {0, 50, 99})
            w.navigate(30)
            self.assertEqual(w.current_record.frame_index, 50)
            merged, conflicts = merge_review(local, returned)
            self.assertFalse(conflicts)
            self.assertEqual(len(merged.active_records(50)), 1)

    def test_legacy_mode_and_review_metadata_retained(self):
        from test_review_package import fixture
        *_, package = fixture()
        package.manifest['package_format_version'] = 1
        package.manifest.pop('package_kind'); package.manifest.pop('package_purpose')
        package.review['frame_notes']['synthetic:10'] = 'legacy note'
        path = Path(self.tmp.name)/'legacy.dvrpkg'; package.save(path)
        self.window.review_manager.open(AnnotationPackage.open(path))
        self.window.change_language('en_US')
        self.assertIn('Annotation Package Mode', self.window.windowTitle())
        self.assertEqual(self.window.review_manager.package.review['frame_notes']['synthetic:10'], 'legacy note')

    def test_package_marker_click_navigates_actual_frame_and_preserves_human_markers(self):
        local, _, package = empty_package()
        w = self.window
        w.review_manager.open(package)
        w.show(); self.app.processEvents()
        slider = w.timeline.slider
        x = next(x for x, frames in slider.marker_columns(slider.target_frames).items() if 50 in frames)
        QTest.mouseClick(slider, Qt.MouseButton.LeftButton, pos=QPoint(x, slider.height()-4))
        self.assertEqual(w.current_record.frame_index, 50)
        self.assertEqual(slider.value(), 50)
        self.assertEqual(w.current_record.timestamp_time64, 1234567890123456839)
        self.assertEqual(slider.marked_frames, set())
        self.assertEqual(package.progress(local.cine_id), (3, 0, 3))
