import hashlib
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import numpy as np
from test_ui_main_window import QT_AVAILABLE, wait_for
from test_ui_annotation_tools import EditorReader
from droplet_vision.annotations import AnnotationDocument, AnnotationRecord
from droplet_vision.display import DisplaySettings

if QT_AVAILABLE:
    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QApplication, QMessageBox
    from droplet_vision.ui.main_window import MainWindow
    from droplet_vision.ui.cine_controller import CineController


@unittest.skipUnless(QT_AVAILABLE, 'Optional Qt unavailable')
class AnnotationEditorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.window = MainWindow(Path(__file__).parent/'fixtures/experimental_taxonomy.json',
                                 controller=CineController(reader_factory=EditorReader))
        self.window.show()
        self.window.open_cine('fake.cine')
        wait_for(lambda: self.window.current_record is not None)
        self.window.annotation_panel.labels.setCurrentRow(0)
        self.editor = self.window.editor
        self.addCleanup(self.close_window)

    def close_window(self):
        with patch.object(QMessageBox, 'warning', return_value=QMessageBox.StandardButton.Discard):
            self.window.close()

    def point(self):
        self.editor.create_annotation('point', {'point': [50, 50]})

    def test_open_shortcuts_with_metadata_focus(self):
        self.window.activateWindow()
        self.window.metadata_panel.setFocus()
        self.app.processEvents()
        for modifier in (Qt.KeyboardModifier.ShiftModifier, Qt.KeyboardModifier.AltModifier):
            with patch('droplet_vision.ui.annotation_editor.QFileDialog.getOpenFileName',
                       return_value=('', '')) as dialog:
                QTest.keyClick(self.window.metadata_panel, Qt.Key.Key_O,
                               Qt.KeyboardModifier.ControlModifier | modifier)
                self.app.processEvents()
                dialog.assert_called_once()

    def test_dirty_cancel_discard_save_and_autosave(self):
        self.point()
        self.assertTrue(self.editor.document.dirty)
        self.assertTrue(self.window.windowTitle().endswith('*'))
        with patch.object(QMessageBox, 'warning', return_value=QMessageBox.StandardButton.Cancel):
            self.assertFalse(self.window.open_cine('other.cine'))
            self.assertFalse(self.window.close_cine())
            self.window.close()
            self.assertTrue(self.window.isVisible())
        self.assertEqual(len(self.editor.document.active_records()), 1)
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)/'annotations.json'
            with patch.object(self.editor.document, 'save', wraps=self.editor.document.save) as save:
                self.editor.autosave()
                self.assertEqual(save.call_args.kwargs, {'mark_saved': False})
                self.assertIn('outputs/annotations/autosave', save.call_args.args[0].as_posix())
            self.assertTrue(self.editor.document.dirty)
            with patch('droplet_vision.ui.annotation_editor.QFileDialog.getSaveFileName', return_value=(str(path), '')), \
                 patch.object(QMessageBox, 'warning', return_value=QMessageBox.StandardButton.Save):
                self.assertTrue(self.editor.confirm_discard())
            self.assertFalse(self.editor.document.dirty)
            self.assertFalse(self.window.windowTitle().endswith('*'))
            self.editor.undo_stack.undo()
            self.assertTrue(self.editor.document.dirty)
            self.editor.undo_stack.redo()
            self.editor.save(path)
            self.assertTrue(self.editor.load(path))
            self.assertEqual(len(self.editor.document.active_records()), 1)
        self.point()
        with patch.object(QMessageBox, 'warning', return_value=QMessageBox.StandardButton.Discard):
            self.assertTrue(self.window.close_cine())
        self.assertIsNone(self.editor.document)

    def test_mismatched_identity_failed_save_and_session_separation(self):
        self.point()
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)/'different.json'
            other = AnnotationDocument('other', 'other.cine', 10, 100, 256, 256)
            other.save(path)
            with self.assertRaisesRegex(ValueError, 'does not match'):
                self.editor.load(path)
            with patch.object(self.editor, 'save_dialog', return_value=False), \
                 patch.object(QMessageBox, 'warning', return_value=QMessageBox.StandardButton.Save):
                self.assertFalse(self.editor.confirm_discard())
            session = Path(folder)/'session.json'
            self.window.save_session(session)
            self.assertNotIn('active_annotation_ids', session.read_text())
            self.assertNotIn('experimental_feature_x', session.read_text())

    def test_locked_layers_and_prediction_derivative(self):
        prediction = AnnotationRecord('fake', 0, 'experimental_feature_x', 'point', {'point': [20, 20]},
                                      source='model', model_id='test_model', confidence=.81)
        doc = self.editor.document
        doc.add_record(prediction, 'prediction')
        self.editor.changed()
        self.editor.select(prediction.annotation_id)
        self.assertFalse(self.editor.can_edit(prediction))
        self.assertEqual(self.editor.handles, [])
        self.assertFalse(self.editor.edit_annotation(prediction.annotation_id, {'point': [30, 30]}))
        self.editor.deactivate_selected()
        self.assertIn(prediction.annotation_id, doc.active_annotation_ids)
        layer = next(layer for layer in self.window.layers if layer.role == 'prediction')
        self.window.layer_panel._set(layer, 'locked', False)
        self.assertTrue(self.editor.edit_annotation(prediction.annotation_id, {'point': [30, 30]}))
        derivative = self.editor.selected_record()
        self.assertEqual(doc.record_layers[derivative.annotation_id], 'reviewed')
        self.assertEqual(derivative.source, 'manual')
        self.assertEqual(derivative.review_status, 'edited')
        self.assertEqual(doc.records.get(prediction.annotation_id).to_dict(), prediction.to_dict())

    def test_all_display_modes_preserve_geometry_raw_and_handles(self):
        self.editor.create_annotation('polygon', {'points': [[20, 20], [100, 20], [100, 100]]})
        self.editor.switch_tool('select')
        before = self.editor.document.to_dict()
        raw = self.window.raw_image.copy()
        coords = [point[:] for _, point, _ in self.editor.handles]
        self.window.canvas.zoom(2)
        self.window.canvas.horizontalScrollBar().setValue(15)
        for mode in ('raw', 'photometric_ref90', 'manual', 'auto_percentile'):
            self.window.display_panel.set_settings(DisplaySettings(mode=mode, gamma=.7))
            self.assertEqual(self.editor.document.to_dict(), before)
            self.assertEqual([point for _, point, _ in self.editor.handles], coords)
            np.testing.assert_array_equal(self.window.raw_image, raw)


@unittest.skipUnless(QT_AVAILABLE and os.environ.get('DROPLET_VISION_TEST_CINE'), 'Real Cine/Qt not enabled')
class RealAnnotationTests(unittest.TestCase):
    def test_real_time64_geometry_save_reload_modes_and_unchanged_source(self):
        app = QApplication.instance() or QApplication([])
        path = Path(os.environ['DROPLET_VISION_TEST_CINE'])
        before = path.stat()
        window = MainWindow(Path(__file__).parent/'fixtures/experimental_taxonomy.json')
        try:
            window.open_cine(path)
            wait_for(lambda: window.current_record is not None)
            window.annotation_panel.labels.setCurrentRow(0)
            editor = window.editor
            time_records = {}
            for index, kind, geometry in ((966, 'point', {'point': [50, 50]}),
                                         (16098, 'bbox', {'bbox': [20, 20, 80, 80]}),
                                         (16739, 'polygon', {'points': [[20, 20], [100, 20], [100, 100]]})):
                window.navigate(min(index, window.metadata.frame_count-1))
                wait_for(lambda: window.current_record.frame_index == min(index, window.metadata.frame_count-1))
                frame = window.current_record
                time_records[frame.frame_index] = (frame.timestamp_time64, frame.timestamp_s)
                self.assertTrue(editor.create_annotation(kind, geometry))
                self.assertEqual(editor.selected_record().geometry, geometry)
            before_geometry = [r.to_dict() for r in editor.document.active_records()]
            digest = hashlib.sha256(window.raw_image.tobytes()).hexdigest()
            for mode in ('raw', 'photometric_ref90', 'manual', 'auto_percentile'):
                window.display_panel.set_settings(DisplaySettings(mode=mode))
                self.assertEqual([r.to_dict() for r in editor.document.active_records()], before_geometry)
                self.assertEqual(hashlib.sha256(window.raw_image.tobytes()).hexdigest(), digest)
            output = Path('outputs/annotations/smoke/annotation_editor_v1_test.annotations.json')
            editor.save(output)
            self.assertTrue(editor.load(output))
            self.assertEqual([r.to_dict() for r in editor.document.active_records()], before_geometry)
            for record in editor.document.active_records():
                self.assertEqual((record.attributes['raw_time64'], record.attributes['relative_timestamp_s']),
                                 time_records[record.frame_index])
        finally:
            with patch.object(QMessageBox, 'warning', return_value=QMessageBox.StandardButton.Discard):
                window.close()
        after = path.stat()
        self.assertEqual((before.st_size, before.st_mtime_ns), (after.st_size, after.st_mtime_ns))
