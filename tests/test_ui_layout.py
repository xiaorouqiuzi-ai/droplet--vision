import os
import json
from pathlib import Path
import unittest
import tempfile
from unittest.mock import patch
import numpy as np
from test_ui_main_window import QT_AVAILABLE, FakeReader, wait_for

if QT_AVAILABLE:
    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QApplication, QMessageBox
    from droplet_vision.ui.main_window import MainWindow
    from droplet_vision.ui.cine_controller import CineController
    from droplet_vision.ui import i18n
    from droplet_vision.display.photometric import PRESET_ID, MODE


class LayoutReader(FakeReader):
    def __init__(self, path):
        super().__init__(path)
        self.metadata.frame_count = 3201
        self.metadata.width = self.metadata.height = 256

    def read_frame(self, index):
        return np.full((256, 256), 40 + index % 100, np.uint8)

    def build_frame_result(self, index):
        frame = super().build_frame_result(index)
        frame.timestamp_time64 = 7130238840138969063 + index
        frame.timestamp_s = index / 4096
        return frame


@unittest.skipUnless(QT_AVAILABLE, 'Qt unavailable')
class LayoutTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        with patch.dict(os.environ, {'DROPLET_VISION_LANGUAGE': 'zh_CN'}):
            self.window = MainWindow(controller=CineController(reader_factory=LayoutReader))
        self.addCleanup(self.close_window)
        self.window.show()
        self.window.open_cine('fake.cine')
        wait_for(lambda: self.window.current_record is not None)
        self.editor = self.window.editor

    def close_window(self):
        with patch.object(QMessageBox, 'warning', return_value=QMessageBox.StandardButton.Discard):
            self.window.close()
        i18n.set_language('en_US')

    def label(self, stable_id):
        labels = self.window.annotation_panel.labels
        for index in range(labels.count()):
            if labels.item(index).data(Qt.ItemDataRole.UserRole) == stable_id:
                labels.setCurrentRow(index)
                return
        self.fail('Missing test label')

    def test_left_forms_right_tools_complete_time64_and_frame_updates(self):
        window = self.window
        self.assertEqual(window.dockWidgetArea(window.info_dock), Qt.DockWidgetArea.LeftDockWidgetArea)
        self.assertEqual(window.dockWidgetArea(window.annotation_dock), Qt.DockWidgetArea.RightDockWidgetArea)
        self.assertTrue(window.info_dock.isAncestorOf(window.metadata_panel))
        self.assertTrue(window.info_dock.isAncestorOf(window.display_panel))
        self.assertTrue(window.annotation_dock.isAncestorOf(window.annotation_panel))
        self.assertTrue(window.annotation_dock.isAncestorOf(window.layer_panel))
        for button in self.editor.tool_buttons.values():
            self.assertTrue(window.annotation_dock.isAncestorOf(button))
            self.assertTrue(button.isVisible())
        values = window.metadata_panel.values
        self.assertEqual(values['filename'].text(), 'fake.cine')
        self.assertEqual(values['resolution'].text(), '256 × 256')
        self.assertEqual(values['raw_time64'].text(), '7130238840138969063')
        self.assertTrue(values['raw_time64'].textInteractionFlags() & Qt.TextInteractionFlag.TextSelectableByMouse)
        window.navigate(1000)
        wait_for(lambda: window.current_record.frame_index == 1000)
        self.assertEqual(values['frame_index'].text(), '1000')
        self.assertEqual(values['raw_time64'].text(), '7130238840138970063')
        self.assertEqual(values['relative_timestamp'].text(), '0.244140625 s')

    def test_label_recommendation_last_tool_and_incompatibility(self):
        self.label('parent_droplet')
        self.assertEqual(self.editor.tool_key, 'polygon')
        self.assertTrue(self.editor.tool_buttons['polygon'].isChecked())
        self.assertIn('当前标签：父液滴', self.window.statusBar().currentMessage())
        self.assertIn('parent_droplet', self.window.annotation_panel.selected.text())
        self.editor.tool_buttons['bbox'].click()
        self.label('internal_cavity_candidate')
        self.editor.tool_buttons['point'].click()
        self.label('parent_droplet')
        self.assertEqual(self.editor.tool_key, 'bbox')
        self.assertFalse(self.editor.actions['point'].isEnabled())
        self.label('internal_cavity_candidate')
        self.assertEqual(self.editor.tool_key, 'point')
        self.assertEqual(sum(a.isChecked() for a in self.editor.actions.values()), 1)

    def test_dynamic_settings_polygon_count_wand_and_list_selection(self):
        self.label('parent_droplet')
        settings = self.editor.tool_settings
        self.editor.tool.mouse_press([20, 20])
        self.editor.tool.mouse_press([100, 20])
        self.assertIn('2', settings.vertex_count.text())
        self.editor.tool.mouse_press([100,100])
        self.editor.tool.commit()
        self.assertEqual(settings.vertex_count.text(), '当前节点数：0')
        self.editor.undo_stack.undo()
        self.assertFalse(self.editor.wand_panel.isVisible())
        self.editor.tool_buttons['magic_wand'].click()
        self.assertEqual(settings.current_key, 'magic_wand')
        self.assertTrue(self.editor.wand_panel.isVisible())
        self.assertFalse(settings.pages['polygon'].isVisible())
        self.editor.create_annotation('polygon', {'points': [[20,20],[100,20],[100,100]]})
        record = self.editor.selected_record()
        self.window.annotation_panel.items.setCurrentRow(-1)
        self.window.annotation_panel.items.setCurrentRow(0)
        self.assertEqual(self.editor.tool_key, 'select')
        self.assertEqual(self.editor.selected_id, record.annotation_id)
        self.assertEqual(len(self.editor.handles), 3)
        self.assertTrue(self.window.annotation_panel.details.isVisible())

    def test_thousand_step_clamp_fixed_shortcuts_and_playback_are_independent(self):
        window = self.window
        combo = window.transport.frame_step
        self.assertEqual([combo.itemData(i) for i in range(combo.count())], [1,10,100,1000])
        combo.setCurrentIndex(3)
        window.transport.next.click()
        wait_for(lambda: window.current_record.frame_index == 1000)
        window.transport.previous.click()
        wait_for(lambda: window.current_record.frame_index == 0)
        window.transport.previous.click()
        wait_for(lambda: window.current_record.frame_index == 0)
        window.navigate(3100)
        wait_for(lambda: window.current_record.frame_index == 3100)
        window.transport.next.click()
        wait_for(lambda: window.current_record.frame_index == 3200)
        window.activateWindow()
        window.canvas.setFocus()
        self.app.processEvents()
        QTest.keyClick(window.canvas, Qt.Key.Key_PageUp, Qt.KeyboardModifier.ControlModifier)
        wait_for(lambda: window.current_record.frame_index == 2200)
        QTest.keyClick(window.canvas, Qt.Key.Key_PageDown, Qt.KeyboardModifier.ControlModifier)
        wait_for(lambda: window.current_record.frame_index == 3200)
        QTest.keyClick(window.canvas, Qt.Key.Key_Left)
        wait_for(lambda: window.current_record.frame_index == 3199)
        QTest.keyClick(window.canvas, Qt.Key.Key_Left, Qt.KeyboardModifier.ShiftModifier)
        wait_for(lambda: window.current_record.frame_index == 3189)
        QTest.keyClick(window.canvas, Qt.Key.Key_PageUp)
        wait_for(lambda: window.current_record.frame_index == 3089)
        window.transport.fps.setCurrentText('20')
        self.assertEqual(window.playback.interval(), 50)
        self.assertEqual(combo.currentData(), 1000)
        self.assertEqual([window.transport.fps.itemText(i) for i in range(window.transport.fps.count())], ['1','2','5','10','15','20','30','1000'])
        window._tick()
        wait_for(lambda: window.current_record.frame_index == 3090)

    def test_1000_review_fps_single_frame_ticks_and_session_roundtrip(self):
        from droplet_vision.annotations import ViewerSession
        window = self.window
        window.transport.frame_step.setCurrentIndex(3)
        window.transport.fps.setCurrentText('1000')
        self.assertEqual(window.playback.interval(), 1)
        self.assertEqual(window.controller.state.playback_fps, 1000)
        window._tick()
        wait_for(lambda: window.current_record.frame_index == 1)
        self.assertEqual(window.transport.frame_step.currentData(), 1000)
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)/'session.json'
            window.save_session(path)
            session = ViewerSession.load(path)
            self.assertEqual(session.ui_state['review_playback_fps'], 1000)
            window.transport.fps.setCurrentText('10')
            window.open_cine('fake.cine', session)
            wait_for(lambda: window.current_record is not None)
            self.assertEqual(window.transport.fps.currentText(), '1000')
            self.assertEqual(window.playback.interval(), 1)

    def test_bilingual_names_stable_preset_and_compact_display_controls(self):
        window = self.window
        self.assertEqual(window.display_panel.mode.currentText(), '亮度标准化（Ref90）')
        self.assertEqual(window.display_panel.mode.currentData(), MODE)
        self.assertEqual(window.controller.photometric.preset_id, PRESET_ID)
        self.assertEqual(PRESET_ID, 'photometric_ref90_v1')
        self.assertFalse(window.display_panel.manual_controls.isVisible())
        self.assertFalse(window.display_panel.advanced.isVisible())
        window.display_panel.advanced_button.click()
        self.assertIn(PRESET_ID, window.display_panel.photometric_info.text())
        self.assertEqual(i18n.tr('Annotation workspace'), '标注工作区')
        self.assertEqual(i18n.tr('Frame step'), '浏览步长')
        with patch.dict(os.environ, {'DROPLET_VISION_LANGUAGE': 'en_US'}):
            english = MainWindow()
        try:
            english.display_panel.show_photometric()
            self.assertEqual(english.display_panel.mode.currentText(), 'Photometric Normalization (Ref90)')
            self.assertEqual(english.annotation_dock.windowTitle(), 'Annotation workspace')
            self.assertEqual(english.transport.frame_step.itemText(3), '1000 frames')
        finally:
            english.close()


@unittest.skipUnless(QT_AVAILABLE and os.environ.get('DROPLET_VISION_LAYOUT_TEST_CINE'), 'Layout real Cine not enabled')
class RealLayoutTests(unittest.TestCase):
    def test_actual_metadata_tools_thousand_step_and_source_unchanged(self):
        app = QApplication.instance() or QApplication([])
        path = Path(os.environ['DROPLET_VISION_LAYOUT_TEST_CINE'])
        before = path.stat()
        with patch.dict(os.environ, {'DROPLET_VISION_LANGUAGE': 'zh_CN'}):
            window = MainWindow()
        try:
            window.open_cine(path)
            wait_for(lambda: window.current_record is not None)
            window.annotation_panel.labels.setCurrentRow(0)
            self.assertEqual(window.editor.tool_key, 'polygon')
            for point in ([20,20],[100,20],[100,100]):
                window.editor.tool.mouse_press(point)
            window.editor.cancel()
            window.editor.tool_buttons['magic_wand'].click()
            self.assertTrue(window.editor.tool_settings.pages['magic_wand'].isVisibleTo(window))
            window.transport.frame_step.setCurrentIndex(3)
            window.transport.next.click()
            expected = min(1000, window.metadata.frame_count-1)
            wait_for(lambda: window.current_record.frame_index == expected)
            for key, expected_text in (('frame_index',str(expected)), ('raw_time64',str(window.current_record.timestamp_time64))):
                self.assertEqual(window.metadata_panel.values[key].text(), expected_text)
            summary = {key: value.text() for key,value in window.metadata_panel.values.items()}
            window.transport.previous.click()
            wait_for(lambda: window.current_record.frame_index == 0)
            window.transport.fps.setCurrentText('1000')
            window.toggle_play()
            wait_for(lambda: window.current_record.frame_index >= min(5, window.metadata.frame_count-1))
            window.pause()
            self.assertLess(window.current_record.frame_index, 1000)
            summary['review_fps'] = window.controller.state.playback_fps
            summary['playback_observed_frame'] = window.current_record.frame_index
            summary['frame_step'] = window.transport.frame_step.currentData()
            summary['display_name'] = window.display_panel.mode.currentText()
            summary['preset_id'] = window.controller.photometric.preset_id
            output = Path('outputs/viewer_smoke/layout_v1_2')
            output.mkdir(parents=True, exist_ok=True)
            (output/'real_metadata.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding='utf-8')
        finally:
            window.close()
            i18n.set_language('en_US')
        after = path.stat()
        self.assertEqual((before.st_size,before.st_mtime_ns),(after.st_size,after.st_mtime_ns))
