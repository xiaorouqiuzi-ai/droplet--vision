import hashlib
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import numpy as np

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from droplet_vision.display import DisplaySettings, apply_display_transform
from droplet_vision.annotations import AnnotationRecord, ViewerSession
from test_ui_main_window import QT_AVAILABLE, FakeReader, wait_for

if QT_AVAILABLE:
    from PySide6.QtWidgets import QApplication, QMessageBox
    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest
    from droplet_vision.ui.main_window import MainWindow
    from droplet_vision.ui.cine_controller import CineController


class DisplayReader(FakeReader):
    def __init__(self, path):
        super().__init__(path)
        self.metadata.width = self.metadata.height = 256

    def read_frame(self, index):
        return np.tile(np.arange(256, dtype=np.uint8), (256, 1))


def canvas_pixels(window):
    image = window.canvas.image_item.pixmap().toImage()
    from PySide6.QtGui import QImage
    image = image.convertToFormat(QImage.Format.Format_Grayscale8)
    return np.frombuffer(image.constBits(), dtype=np.uint8).reshape(image.height(), image.bytesPerLine())[:, :image.width()].copy()


@unittest.skipUnless(QT_AVAILABLE, 'Optional Qt unavailable')
class DisplayUiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.window = MainWindow(controller=CineController(reader_factory=DisplayReader))
        self.addCleanup(self.window.close)
        self.window.show()
        self.window.open_cine('fake.cine')
        wait_for(lambda: self.window.current_record is not None)

    def test_panel_values_shortcuts_and_reset_preserve_observation(self):
        panel = self.window.display_panel
        panel.mode.setCurrentIndex(panel.mode.findData('manual'))
        panel.brightness.setValue(25)
        panel.contrast.setValue(140)
        panel.gamma.setValue(70)
        expected = DisplaySettings(mode='manual', brightness=.25, contrast=1.4, gamma=.7)
        self.assertEqual(panel.settings, expected)
        self.assertEqual(panel.value_labels['brightness'].text(), 'Brightness: +25')
        self.window.add_bookmark(note='keep')
        self.window.session.notes = 'keep notes'
        self.window.canvas.zoom(2)
        transform = self.window.canvas.transform()
        self.window.canvas.setFocus()
        QTest.keyClick(self.window.canvas, Qt.Key.Key_R)
        self.assertEqual(panel.settings.mode, 'raw')
        QTest.keyClick(self.window.canvas, Qt.Key.Key_E)
        self.assertEqual(panel.settings, expected)
        panel.reset_button.click()
        self.assertEqual(panel.settings, DisplaySettings())
        self.assertEqual(self.window.current_record.frame_index, 0)
        self.assertEqual(self.window.canvas.transform(), transform)
        self.assertEqual(self.window.session.notes, 'keep notes')
        self.assertEqual(len(self.window.session.bookmarks), 1)

    def test_no_reads_raw_cache_and_overlay_coordinates_unchanged(self):
        window = self.window
        raw = window.raw_image
        before = raw.copy()
        cached = window.controller.cache.get(0)
        record = AnnotationRecord('fake', 0, 'arbitrary', 'polygon', {'points': [[20, 20], [100, 20], [100, 100]]})
        window.layers[0].annotations = [record]
        original_record = record.to_dict()
        window.refresh_overlays()
        overlay = window.canvas.overlays.items[0]
        polygon = overlay.polygon()
        window.canvas.zoom(3)
        window.canvas.horizontalScrollBar().setValue(15)
        window.canvas.verticalScrollBar().setValue(12)
        view_transform = window.canvas.transform()
        position = (window.canvas.horizontalScrollBar().value(), window.canvas.verticalScrollBar().value())
        with patch.object(window.controller._reader, 'read_frame', side_effect=AssertionError('Display must not decode')):
            for mode in ('manual', 'auto_percentile', 'raw'):
                settings = DisplaySettings(mode=mode, brightness=.25, contrast=1.4, gamma=.7)
                window.display_panel.set_settings(settings)
                self.assertEqual(overlay.polygon(), polygon)
                self.assertEqual(record.to_dict(), original_record)
                self.assertEqual(window.canvas.transform(), view_transform)
                self.assertEqual((window.canvas.horizontalScrollBar().value(), window.canvas.verticalScrollBar().value()), position)
                np.testing.assert_array_equal(canvas_pixels(window), apply_display_transform(raw, settings))
                np.testing.assert_array_equal(raw, before)
                self.assertIs(window.controller.cache.get(0), cached)
                np.testing.assert_array_equal(cached, before)
            window.display_panel.mode.setCurrentIndex(window.display_panel.mode.findData('manual'))
            for slider in (window.display_panel.brightness, window.display_panel.contrast, window.display_panel.gamma):
                slider.setValue(slider.value() + 1)

    def test_session_restore_old_session_invalid_state_and_percentile_controls(self):
        panel = self.window.display_panel
        panel.set_settings(DisplaySettings(mode='auto_percentile', percentile_low=2, percentile_high=98))
        panel.percentile_low.setValue(99)
        self.assertGreater(panel.settings.percentile_high, panel.settings.percentile_low)
        settings = panel.settings
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'session.json'
            self.window.save_session(path)
            session = ViewerSession.load(path)
        self.window.open_cine('fake.cine', session)
        wait_for(lambda: self.window.current_record is not None)
        self.assertEqual(panel.settings, settings)
        self.assertEqual(panel.percentile_low.value(), settings.percentile_low)
        session.ui_state.pop('display')
        self.window.open_cine('fake.cine', session)
        wait_for(lambda: self.window.current_record is not None)
        self.assertEqual(panel.settings, DisplaySettings())
        session.ui_state['display'] = {'gamma': 0}
        with patch.object(QMessageBox, 'warning') as warning:
            self.window.open_cine('fake.cine', session)
            wait_for(lambda: self.window.current_record is not None)
            self.assertTrue(warning.called)
        self.assertEqual(panel.settings, DisplaySettings())


@unittest.skipUnless(QT_AVAILABLE and os.environ.get('DROPLET_VISION_TEST_CINE'), 'Real Cine/Qt not enabled')
class RealDisplayTests(unittest.TestCase):
    def test_all_modes_four_frames_raw_export_cache_and_timing(self):
        from PIL import Image
        from droplet_vision.cine import CineReader
        app = QApplication.instance() or QApplication([])
        path = Path(os.environ['DROPLET_VISION_TEST_CINE'])
        before = path.stat()
        window = MainWindow()
        try:
            window.open_cine(path)
            wait_for(lambda: window.current_record is not None)
            with CineReader(path) as reader, tempfile.TemporaryDirectory() as temp:
                for index in dict.fromkeys((0, min(16098, len(reader)-1), min(16739, len(reader)-1), len(reader)-1)):
                    window.navigate(index)
                    wait_for(lambda: window.current_record.frame_index == index)
                    raw = window.raw_image
                    expected = reader.read_frame(index)
                    raw_hash = hashlib.sha256(raw.tobytes()).hexdigest()
                    record = reader.build_frame_result(index)
                    for mode in ('raw', 'manual', 'auto_percentile'):
                        settings = DisplaySettings(mode=mode, brightness=.1, contrast=1.4, gamma=.7)
                        with patch.object(window.controller._reader, 'read_frame', side_effect=AssertionError('Unexpected Cine read')):
                            window.display_panel.set_settings(settings)
                            np.testing.assert_array_equal(canvas_pixels(window), apply_display_transform(expected, settings))
                            output = Path(temp) / f'{index}_{mode}.png'
                            window.export_frame(output)
                        with Image.open(output) as exported:
                            np.testing.assert_array_equal(np.asarray(exported), expected)
                        self.assertEqual(hashlib.sha256(raw.tobytes()).hexdigest(), raw_hash)
                        np.testing.assert_array_equal(window.controller.cache.get(index), expected)
                        self.assertEqual(window.current_record.timestamp_s, record.timestamp_s)
                        self.assertIn(record.timing_status.value, window.time_label.text())
        finally:
            window.close()
        after = path.stat()
        self.assertEqual((before.st_size, before.st_mtime_ns), (after.st_size, after.st_mtime_ns))
