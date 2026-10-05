import os
import sys
import time
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
os.environ.setdefault('DROPLET_VISION_LANGUAGE', 'en_US')  # deterministic legacy UI assertions; i18n tests exercise Chinese separately
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
try:
    import numpy as np
    from PySide6.QtWidgets import QApplication, QMessageBox
    from PySide6.QtCore import Qt, QPoint
    from PySide6.QtTest import QTest
    from droplet_vision.ui.main_window import MainWindow
    from droplet_vision.ui.cine_controller import CineController
    from droplet_vision.ui.display import to_qimage
    QT_AVAILABLE = True
except ImportError:
    QT_AVAILABLE = False

from droplet_vision.annotations import AnnotationRecord
from droplet_vision.schema import FrameResult
from droplet_vision.cine.metadata import CineMetadata
from droplet_vision.cine.timing import summarize_timing


def wait_for(predicate, timeout=10):
    limit = time.monotonic() + timeout
    while not predicate() and time.monotonic() < limit:
        QApplication.processEvents()
        time.sleep(.005)
    if not predicate():
        raise AssertionError('Timed out waiting for UI worker')


class FakeReader:
    def __init__(self, path):
        self.metadata = CineMetadata(filename='fake.cine', frame_count=20, width=12, height=8,
                                     file_size_bytes=100, pixel_dtype='uint8')
        self.timing_summary = summarize_timing([i * 2**32 for i in range(20)], 2)
        self.closed = False

    def read_frame(self, index):
        if index == 1:
            time.sleep(.1)
        return np.full((8, 12), index, dtype=np.uint8)

    def build_frame_result(self, index):
        return FrameResult('fake', index, timestamp_s=float(index), timestamp_time64=index * 2**32,
                           timing_status=self.timing_summary.timing_status)

    def close(self):
        self.closed = True


@unittest.skipUnless(QT_AVAILABLE, 'Optional Qt/NumPy unavailable')
class MainWindowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.controller = CineController(reader_factory=FakeReader)
        self.window = MainWindow(Path(__file__).parent / 'fixtures/experimental_taxonomy.json', controller=self.controller)
        self.addCleanup(self.window.close)
        self.window.show()
        self.app.processEvents()

    def open_fake(self):
        self.window.open_cine('fake.cine')
        wait_for(lambda: self.window.current_record is not None)

    def test_empty_window_dynamic_taxonomy_and_display(self):
        self.assertIsNone(self.window.current_record)
        self.assertFalse(self.window.timeline.isEnabled())
        labels = self.window.annotation_panel.labels
        self.assertEqual(labels.item(0).data(Qt.ItemDataRole.UserRole), 'experimental_feature_x')
        raw = np.arange(96, dtype=np.uint8).reshape(8, 12)
        original = raw.copy()
        self.window.canvas.set_image(raw)
        self.window.canvas.zoom(1.2)
        self.window.canvas.fit_image()
        np.testing.assert_array_equal(raw, original)
        self.assertEqual(self.window.canvas.image_item.pixmap().size().width(), 12)
        sixteen = np.array([[0, 65535]], dtype=np.uint16)
        self.assertEqual(to_qimage(sixteen).pixelColor(1, 0).red(), 255)
        self.assertEqual(sixteen[0, 1], 65535)

    def test_navigation_bookmark_session_overlay(self):
        self.open_fake()
        self.window.timeline.spinbox.setValue(5)
        wait_for(lambda: self.window.current_record.frame_index == 5)
        self.assertEqual(self.window.timeline.slider.value(), 5)
        self.window.step(100)
        wait_for(lambda: self.window.current_record.frame_index == 19)
        self.window.navigate(0)
        wait_for(lambda: self.window.current_record.frame_index == 0)
        self.window.timeline.slider.setValue(7)
        wait_for(lambda: self.window.current_record.frame_index == 7)
        self.window.add_bookmark(note='note', tags=['new_tag'])
        with tempfile.TemporaryDirectory() as temp:
            self.window.save_session(Path(temp) / 'session.json')
            self.assertIn('new_tag', (Path(temp) / 'session.json').read_text())
        geometries = [('point', {'point': [2, 2]}), ('bbox', {'bbox': [1, 1, 4, 4]}),
                      ('polygon', {'points': [[1, 1], [5, 1], [3, 5]]})]
        self.window.layers[0].annotations = [AnnotationRecord('fake', 7, 'experimental_feature_x', kind, geom)
                                            for kind, geom in geometries]
        self.window.refresh_overlays()
        self.assertEqual(len(self.window.canvas.overlays.items), 3)
        self.window.layers[0].visible = False
        self.window.refresh_overlays()
        self.assertEqual(len(self.window.canvas.overlays.items), 0)

    def test_late_response_cannot_replace_newer_frame(self):
        self.open_fake()
        received = []
        self.controller.frame_ready.connect(lambda index, image, record: received.append(index))
        self.window.navigate(1)
        self.window.navigate(8)
        self.window.navigate(9)
        wait_for(lambda: self.window.current_record.frame_index == 9)
        self.assertEqual(received, [9])
        self.assertEqual(self.window.raw_image[0, 0], 9)

    def test_playback_stop_and_close_during_read(self):
        self.open_fake()
        self.window.set_playback_fps(30)
        self.assertEqual(self.window.playback.interval(), 33)
        self.window.navigate(18)
        wait_for(lambda: self.window.current_record.frame_index == 18)
        self.window.toggle_play()
        wait_for(lambda: self.window.current_record.frame_index == 19)
        self.assertFalse(self.window.playback.isActive())
        self.window.navigate(1)
        self.window.close_cine()
        wait_for(lambda: self.controller._reader is None)
        self.assertIsNone(self.window.raw_image)

    def test_debounce_preserves_new_slider_intent(self):
        self.open_fake()
        self.window.timeline.slider.setValue(12)
        self.window._frame_ready(0, np.zeros((8, 12), dtype=np.uint8), FrameResult('fake', 0))
        self.assertEqual(self.window.timeline.slider.value(), 12)
        wait_for(lambda: self.window.current_record.frame_index == 12)

    def test_middle_drag_pan_and_keyboard_navigation(self):
        self.open_fake()
        canvas = self.window.canvas
        canvas.set_image(np.zeros((512, 512), dtype=np.uint8), fit=True)
        canvas.zoom(3)
        self.app.processEvents()
        canvas.horizontalScrollBar().setValue(canvas.horizontalScrollBar().maximum() // 2)
        before = canvas.horizontalScrollBar().value()
        QTest.mousePress(canvas.viewport(), Qt.MouseButton.MiddleButton, pos=QPoint(150, 150))
        QTest.mouseMove(canvas.viewport(), QPoint(200, 150))
        QTest.mouseRelease(canvas.viewport(), Qt.MouseButton.MiddleButton, pos=QPoint(200, 150))
        self.assertNotEqual(canvas.horizontalScrollBar().value(), before)
        self.assertIsNone(canvas._pan_start)
        canvas.setFocus()
        QTest.keyClick(canvas, Qt.Key.Key_End)
        wait_for(lambda: self.window.current_record.frame_index == 19)
        QTest.keyClick(canvas, Qt.Key.Key_Home)
        wait_for(lambda: self.window.current_record.frame_index == 0)

    def test_dialog_defaults_use_existing_ignored_directories(self):
        self.open_fake()
        with patch('droplet_vision.ui.main_window.QFileDialog.getSaveFileName', return_value=('', '')) as dialog:
            self.window.export_dialog()
            suggested = Path(dialog.call_args.args[2])
            self.assertEqual(suggested.parent, Path('outputs/viewer_frames'))
            self.assertTrue(suggested.parent.is_dir())
            self.window.save_session_dialog()
            suggested = Path(dialog.call_args.args[2])
            self.assertEqual(suggested.parent, Path('outputs/viewer_sessions'))
            self.assertTrue(suggested.parent.is_dir())

    def test_open_error_is_reported_without_crashing(self):
        self.controller._reader_factory = lambda path: (_ for _ in ()).throw(ValueError('test error'))
        with patch.object(QMessageBox, 'warning') as warning:
            self.window.open_cine('bad.cine')
            wait_for(lambda: warning.called)
        self.assertIsNone(self.window.current_record)


@unittest.skipUnless(QT_AVAILABLE and os.environ.get('DROPLET_VISION_TEST_CINE'), 'Real Cine/Qt not enabled')
class RealViewerTests(unittest.TestCase):
    def test_real_frames_export_session_and_reopen(self):
        from PIL import Image
        from droplet_vision.cine import CineReader
        from droplet_vision.annotations import ViewerSession
        app = QApplication.instance() or QApplication([])
        path = Path(os.environ['DROPLET_VISION_TEST_CINE'])
        before = path.stat()
        window = MainWindow()
        try:
            window.open_cine(path)
            wait_for(lambda: window.current_record is not None)
            with CineReader(path) as expected:
                for index in (0, min(16098, len(expected) - 1), len(expected) - 1):
                    window.navigate(index)
                    wait_for(lambda: window.current_record.frame_index == index)
                    np.testing.assert_array_equal(window.raw_image, expected.read_frame(index))
                    record = expected.build_frame_result(index)
                    self.assertEqual(window.current_record.timestamp_s, record.timestamp_s)
                    self.assertIn(record.timing_status.value, window.time_label.text())
                with tempfile.TemporaryDirectory() as temp:
                    export = Path(temp) / 'frame.png'
                    window.export_frame(export)
                    np.testing.assert_array_equal(np.asarray(Image.open(export)), window.raw_image)
                    window.add_bookmark(tags=['test_tag'])
                    session_path = Path(temp) / 'session.json'
                    window.save_session(session_path)
                    session = ViewerSession.load(session_path)
                    window.close_cine()
                    window.open_cine(path, session)
                    wait_for(lambda: window.current_record is not None)
                    self.assertEqual(window.current_record.frame_index, len(expected) - 1)
                    self.assertEqual(len(window.session.bookmarks), 1)
        finally:
            window.close()
        after = path.stat()
        self.assertEqual((before.st_size, before.st_mtime_ns), (after.st_size, after.st_mtime_ns))
