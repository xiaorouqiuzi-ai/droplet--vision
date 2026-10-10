"""Clock-controlled review progression, bounded decoding and presentation state."""
import json
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

from test_ui_main_window import QT_AVAILABLE, wait_for
import test_ui_layout as layout_tests
from droplet_vision.ui.review_playback import ReviewPlayback

if QT_AVAILABLE:
    from PySide6.QtCore import Qt, QPoint
    from PySide6.QtTest import QTest
    from droplet_vision.annotations import ViewerSession, AnnotationRecord


class ReviewClockTests(unittest.TestCase):
    def test_rates_elapsed_and_clamp(self):
        clock = [0.0]
        playback = ReviewPlayback(lambda: clock[0])
        for rate in (10, 1000):
            clock[0] = 20.0
            playback.start(42, rate)
            clock[0] = 21.0
            self.assertEqual(playback.desired_frame(32196), 42 + rate)
        clock[0] = 100.0
        self.assertEqual(playback.desired_frame(32196), 32195)
        playback.stop()
        clock[0] = 500.0
        playback.start(123, 1000)
        self.assertEqual(playback.desired_frame(32196), 123)


@unittest.skipUnless(QT_AVAILABLE, 'Qt unavailable')
class ReviewPlaybackTests(unittest.TestCase):
    setUpClass = layout_tests.LayoutTests.__dict__['setUpClass']
    close_window = layout_tests.LayoutTests.close_window

    def setUp(self):
        layout_tests.LayoutTests.setUp(self)
        self.now = [0.0]
        self.window.review_clock.now = lambda: self.now[0]

    def play(self, rate=1000):
        wait_for(lambda: not self.window.controller.busy)
        self.window.transport.fps.setCurrentText(str(rate))
        self.window.toggle_play()
        # Tests drive the same callback explicitly; no one-second real sleeps.
        self.window.playback.stop()

    def advance(self, seconds, expected):
        self.now[0] += seconds
        self.window._tick()
        wait_for(lambda: self.window.current_record.frame_index == expected)

    def test_one_second_progress_not_one_thousand_renders_and_raw_provenance(self):
        window = self.window
        annotation = AnnotationRecord('fake', 0, 'parent_droplet', 'polygon',
                                      {'points': [[10,10],[90,10],[90,90]]})
        window.editor.document.add_record(annotation, 'manual')
        window.editor.changed()
        before = window.editor.document.to_dict()
        raw = window.raw_image.copy()
        for rate in (10,1000):
            window.navigate(0)
            wait_for(lambda: window.current_record.frame_index == 0)
            self.play(rate)
            with patch.object(window.controller, 'request_frame', wraps=window.controller.request_frame) as request:
                self.advance(1.0, rate)
                self.assertEqual(request.call_count, 1)
            self.assertEqual(window.timeline.slider.value(), rate)
            self.assertEqual(window.current_record.timestamp_time64, 7130238840138969063 + rate)
            self.assertEqual(window.current_record.timestamp_s, rate / 4096)
            self.assertIn(str(window.current_record.timestamp_time64),
                          window.metadata_panel.values['raw_time64'].text())
            window.pause()
        self.assertEqual(window.editor.document.to_dict(), before)
        self.assertTrue((window.controller.cache.get(0) == raw).all())

    def test_busy_decode_keeps_only_latest_target_and_pause_discards_inflight(self):
        window = self.window
        reader = window.controller._reader
        original = reader.read_frame
        entered, release = threading.Event(), threading.Event()
        decoded = []
        def blocked(index):
            decoded.append(index)
            entered.set()
            if not release.wait(5):
                raise RuntimeError('test gate timeout')
            return original(index)
        with patch.object(reader, 'read_frame', side_effect=blocked):
            try:
                self.play()
                self.now[0] = .1
                window._tick()
                wait_for(entered.is_set)
                for moment in (.2, .5, 1.0):
                    self.now[0] = moment
                    window._tick()
                self.assertEqual(window._review_desired, 1000)
                self.assertEqual(decoded, [100])
                self.assertIsNone(window.controller._pending)
                self.assertEqual(window.timeline.slider.value(), 0)
                self.assertEqual(window.current_record.frame_index, 0)
                self.assertFalse(window.editor.ready)
                window.pause()
                self.assertTrue(window.editor.ready)
                release.set()
                wait_for(lambda: not window.controller.busy)
                self.assertEqual(window.current_record.frame_index, 0)
            finally:
                release.set()
        self.now[0] = 100
        self.play()
        self.advance(1.0, 1000)

    def test_controller_newest_request_wins_and_stale_result_ignored(self):
        window = self.window
        entered, release = threading.Event(), threading.Event()
        reader = window.controller._reader
        original = reader.read_frame
        def blocked(index):
            if index == 100:
                entered.set()
                if not release.wait(5):
                    raise RuntimeError('test gate timeout')
            return original(index)
        received = []
        window.controller.frame_ready.connect(lambda index, *_: received.append(index))
        with patch.object(reader, 'read_frame', side_effect=blocked):
            try:
                window.controller.request_frame(100)
                wait_for(entered.is_set)
                for index in range(101, 1001):
                    window.controller.request_frame(index)
                self.assertEqual(len(window.controller._pending), 3)  # One task tuple.
                release.set()
                wait_for(lambda: window.current_record.frame_index == 1000)
                self.assertEqual(received, [1000])
            finally:
                release.set()

    def test_pause_resume_manual_jumps_markers_and_end(self):
        window = self.window
        self.play()
        self.advance(.2, 200)
        window.pause()
        self.now[0] = 500
        self.play()
        self.assertEqual(window.review_clock.start_frame, 200)
        self.advance(.1, 300)
        window.transport.jump_buttons[1000].click()
        wait_for(lambda: window.current_record.frame_index == 1300)
        self.assertFalse(window.review_clock.active)
        self.assertEqual(window.controller.state.playback_fps, 1000)
        self.play()
        window.timeline.slider.set_markers({100})
        x = next(iter(window.timeline.slider.marker_positions({100})))
        QTest.mouseClick(window.timeline.slider, Qt.MouseButton.LeftButton, pos=QPoint(x,4))
        wait_for(lambda: window.current_record.frame_index == 100)
        self.assertFalse(window.review_clock.active)
        self.play()
        self.advance(10, 3200)
        self.assertFalse(window.review_clock.active)
        self.assertFalse(window.playback.isActive())

    def test_session_legacy_read_new_key_write(self):
        window = self.window
        legacy = ViewerSession('fake.cine', 100, 3201,
                               ui_state={'review_playback_fps': 1000})
        window.open_cine('fake.cine', legacy)
        wait_for(lambda: window.current_record is not None)
        self.assertEqual(window.transport.fps.currentText(), '1000')
        self.assertEqual(window.playback.interval(), 16)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'session.json'
            window.save_session(path)
            data = json.loads(path.read_text())
            self.assertEqual(data['ui_state']['review_speed_frames_per_second'],1000)
            self.assertNotIn('review_playback_fps',data['ui_state'])
            restored = ViewerSession.load(path)
            window.open_cine('fake.cine', restored)
            wait_for(lambda: window.current_record is not None)
            self.assertEqual(window.controller.state.playback_fps,1000)
