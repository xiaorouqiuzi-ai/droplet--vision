import hashlib
import json
import os
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch

import numpy as np
from PIL import Image
from test_ui_main_window import QT_AVAILABLE, FakeReader, wait_for
from test_ui_display import canvas_pixels
from droplet_vision.annotations import AnnotationRecord, ViewerSession
from droplet_vision.display.photometric import MODE, apply_locked_gain, cine_reference_index

if QT_AVAILABLE:
    from PySide6.QtWidgets import QApplication
    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest
    from droplet_vision.ui.main_window import MainWindow
    from droplet_vision.ui.cine_controller import CineController


class PhotometricReader(FakeReader):
    def __init__(self, path):
        super().__init__(path)
        self.metadata.frame_count = 100
        self.calls = []

    def read_frame(self, index):
        self.calls.append(index)
        return np.full((8, 12), 40 + index, dtype=np.uint8)


@unittest.skipUnless(QT_AVAILABLE, 'Optional Qt unavailable')
class PhotometricUiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def window(self, factory=PhotometricReader):
        window = MainWindow(controller=CineController(reader_factory=factory))
        self.addCleanup(window.close)
        window.show()
        return window

    def open(self, window):
        window.open_cine('fake.cine')
        wait_for(lambda: window.current_record is not None)

    def test_default_locked_gain_recalculate_and_navigation(self):
        window = self.window()
        self.open(window)
        controller = window.controller
        reference = controller.photometric
        self.assertEqual(window.display_panel.settings.mode, MODE)
        self.assertEqual(reference.reference_frame_index, 3)
        self.assertEqual(controller._reader.calls, [3, 0])
        with patch('droplet_vision.ui.cine_controller.estimate_reference', side_effect=AssertionError('No re-estimation')):
            for index in (10, 90, 20):
                window.navigate(index)
                wait_for(lambda: window.current_record.frame_index == index)
                self.assertIs(controller.photometric, reference)
                np.testing.assert_array_equal(canvas_pixels(window), apply_locked_gain(window.raw_image, reference))
        window.display_panel.recalculate_button.click()
        window.navigate(30)
        window.navigate(40)
        wait_for(lambda: controller.photometric is not None and window.current_record.frame_index == 40)
        self.assertIsNot(controller.photometric, reference)
        self.assertEqual(controller._reader.calls.count(3), 2)
        self.assertEqual(controller.photometric.gain_used, reference.gain_used)

    def test_raw_switch_overlay_cache_export_and_session(self):
        window = self.window()
        self.open(window)
        raw = window.raw_image.copy()
        cached = window.controller.cache.get(0)
        geometries = [('point', {'point': [2, 2]}), ('bbox', {'bbox': [1, 1, 4, 4]}),
                      ('polygon', {'points': [[1, 1], [5, 1], [3, 5]]})]
        annotations = [AnnotationRecord('fake', 0, 'any_label', kind, shape) for kind, shape in geometries]
        window.layers[0].annotations = annotations
        window.refresh_overlays()
        original = [a.to_dict() for a in annotations]
        items = window.canvas.overlays.items[:]
        bounds = [item.sceneBoundingRect() for item in items]
        window.canvas.zoom(2)
        transform = window.canvas.transform()
        with patch.object(window.controller._reader, 'read_frame', side_effect=AssertionError('Mode switch must not read')):
            window.canvas.setFocus()
            for key, mode in ((Qt.Key.Key_R, 'raw'), (Qt.Key.Key_P, MODE),
                              (Qt.Key.Key_R, 'raw'), (Qt.Key.Key_E, MODE)):
                QTest.keyClick(window.canvas, key)
                self.assertEqual(window.display_panel.settings.mode, mode)
                self.assertEqual([a.to_dict() for a in annotations], original)
                self.assertEqual([item.sceneBoundingRect() for item in items], bounds)
                self.assertEqual(window.canvas.transform(), transform)
                np.testing.assert_array_equal(window.raw_image, raw)
                self.assertIs(window.controller.cache.get(0), cached)
                np.testing.assert_array_equal(cached, raw)
            with tempfile.TemporaryDirectory() as folder:
                output = Path(folder) / 'raw.png'
                window.export_frame(output)
                with Image.open(output) as im:
                    np.testing.assert_array_equal(np.array(im), raw)
                session_path = Path(folder) / 'session.json'
                window.save_session(session_path)
                session = ViewerSession.load(session_path)
        self.assertEqual(session.ui_state['display']['mode'], MODE)
        self.assertEqual(session.ui_state['photometric']['gain_used'], window.controller.photometric.gain_used)
        # Stored gain is provenance, not trusted computation: reopen must read the reference.
        session.ui_state['photometric']['gain_used'] = 999
        window.open_cine('fake.cine', session)
        wait_for(lambda: window.current_record is not None)
        self.assertNotEqual(window.controller.photometric.gain_used, 999)
        self.assertEqual(window.display_panel.settings.mode, MODE)

    def test_reference_failure_zero_and_read_error_fall_back_raw(self):
        for failure in ('zero', 'read'):
            class BadReference(PhotometricReader):
                def read_frame(self, index):
                    if index == 3:
                        if failure == 'read':
                            raise OSError('reference read failed')
                        return np.zeros((8, 12), dtype=np.uint8)
                    return super().read_frame(index)
            window = self.window(BadReference)
            self.open(window)
            self.assertIsNone(window.controller.photometric)
            self.assertEqual(window.display_panel.settings.mode, 'raw')
            self.assertIn('PHOTOMETRIC_REFERENCE_FAILED', window.display_panel.photometric_info.text())
            self.assertIn('Raw display used', window.statusBar().currentMessage())
            np.testing.assert_array_equal(canvas_pixels(window), window.raw_image)
            window.display_panel.show_photometric()
            self.assertEqual(window.display_panel.settings.mode, 'raw')
            window.close()

    def test_stale_open_reference_and_user_raw_override(self):
        entered, release = threading.Event(), threading.Event()
        class SlowReader(PhotometricReader):
            def __init__(self, path):
                super().__init__(path)
                self.slow = path == 'slow.cine'
            def read_frame(self, index):
                if self.slow and index == 3:
                    entered.set()
                    release.wait(5)
                    return np.full((8, 12), 100, dtype=np.uint8)
                return super().read_frame(index)
        window = self.window(SlowReader)
        self.addCleanup(release.set)
        window.open_cine('slow.cine')
        wait_for(entered.is_set)
        window.open_cine('other.cine')
        window.display_panel.show_raw()
        release.set()
        wait_for(lambda: window.current_record is not None)
        self.assertEqual(window.controller.photometric.reference_p90, 43)
        self.assertEqual(window.display_panel.settings.mode, 'raw')

    def test_stale_recalculation_cannot_apply_to_new_cine(self):
        entered, release = threading.Event(), threading.Event()
        window = self.window()
        self.addCleanup(release.set)
        self.open(window)
        old_reader = window.controller._reader
        original_read = old_reader.read_frame
        def slow(index):
            entered.set()
            release.wait(5)
            return np.full_like(original_read(index), 100)
        with patch.object(old_reader, 'read_frame', side_effect=slow):
            window.controller.recalculate_reference()
            wait_for(entered.is_set)
            window.open_cine('new.cine')
            release.set()
            wait_for(lambda: window.current_record is not None)
        self.assertTrue(old_reader.closed)
        self.assertEqual(window.controller.photometric.reference_p90, 43)


@unittest.skipUnless(QT_AVAILABLE and os.environ.get('DROPLET_VISION_TEST_CINE'), 'Real Cine/Qt not enabled')
class RealPhotometricTests(unittest.TestCase):
    def test_real_locked_reference_four_frames_export_and_reopen(self):
        from droplet_vision.cine import CineReader
        app = QApplication.instance() or QApplication([])
        path = Path(os.environ['DROPLET_VISION_TEST_CINE'])
        before = path.stat()
        window = MainWindow()
        try:
            window.open_cine(path)
            wait_for(lambda: window.current_record is not None)
            locked = window.controller.photometric
            self.assertIsNotNone(locked)
            self.assertEqual(window.display_panel.settings.mode, MODE)
            with CineReader(path) as reader, tempfile.TemporaryDirectory() as folder:
                index = cine_reference_index(len(reader))
                self.assertEqual(locked.reference_frame_index, index)
                self.assertEqual(locked.reference_p90, float(np.percentile(reader.read_frame(index), 90)))
                for index in dict.fromkeys((0, min(16098, len(reader)-1), min(16739, len(reader)-1), len(reader)-1)):
                    window.navigate(index)
                    wait_for(lambda: window.current_record.frame_index == index)
                    raw = window.raw_image
                    digest = hashlib.sha256(raw.tobytes()).hexdigest()
                    expected = reader.read_frame(index)
                    with patch.object(window.controller._reader, 'read_frame', side_effect=AssertionError('No display decode')):
                        window.display_panel.show_raw()
                        np.testing.assert_array_equal(canvas_pixels(window), expected)
                        window.display_panel.show_photometric()
                        np.testing.assert_array_equal(canvas_pixels(window), apply_locked_gain(expected, locked))
                        output = Path(folder) / f'{index}.png'
                        window.export_frame(output)
                    with Image.open(output) as im:
                        np.testing.assert_array_equal(np.array(im), expected)
                    self.assertIs(window.controller.photometric, locked)
                    self.assertEqual(hashlib.sha256(raw.tobytes()).hexdigest(), digest)
                    np.testing.assert_array_equal(window.controller.cache.get(index), expected)
                    self.assertEqual(window.current_record.timestamp_s, reader.build_frame_result(index).timestamp_s)
                report = {**locked.to_dict(), 'frame_count': len(reader),
                          'timing_status': reader.timing_summary.timing_status.value}
            window.close_cine()
            window.open_cine(path)
            wait_for(lambda: window.current_record is not None)
            self.assertEqual(window.controller.photometric.gain_used, locked.gain_used)
            print('REF90_REAL_INTEGRATION ' + json.dumps(report), flush=True)
        finally:
            window.close()
        after = path.stat()
        self.assertEqual((before.st_size, before.st_mtime_ns), (after.st_size, after.st_mtime_ns))
