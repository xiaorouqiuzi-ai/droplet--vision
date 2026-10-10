import hashlib
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import numpy as np
from test_ui_main_window import QT_AVAILABLE, wait_for
from test_ui_layout import LayoutReader
from droplet_vision.annotations.document import AnnotationDocument
from droplet_vision.annotations.schema import AnnotationRecord

if QT_AVAILABLE:
    from PySide6.QtCore import Qt, QPointF
    from PySide6.QtWidgets import QApplication, QMessageBox, QGraphicsItem, QGraphicsRectItem
    from PySide6.QtTest import QTest
    from droplet_vision.ui.main_window import MainWindow
    from droplet_vision.ui.cine_controller import CineController
    from droplet_vision.ui.panels.workflow_panel import CustomSchemeDialog
    from droplet_vision.display import DisplaySettings
    from droplet_vision.ui import i18n


@unittest.skipUnless(QT_AVAILABLE, 'Qt unavailable')
class WorkflowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        with patch.dict(os.environ, {'DROPLET_VISION_LANGUAGE': 'zh_CN'}):
            self.window = MainWindow(controller=CineController(reader_factory=LayoutReader))
        self.window.show()
        self.window.open_cine('fake.cine')
        wait_for(lambda: self.window.current_record is not None)
        self.editor = self.window.editor
        self.workflow = self.editor.workflow
        self.window.annotation_panel.labels.setCurrentRow(0)
        self.addCleanup(self.close_window)

    def close_window(self):
        with patch.object(QMessageBox, 'warning', return_value=QMessageBox.StandardButton.Discard):
            self.window.close()
        i18n.set_language('en_US')

    def polygon(self):
        self.workflow.instance_name.setText('Parent_01')
        self.editor.create_annotation('polygon', {'points': [[20,20], [100,20], [100,100], [20,100]]})
        self.editor.switch_tool('select')
        return self.editor.selected_record()

    def test_scheme_explicit_apply_cancel_and_legacy_preservation(self):
        old = AnnotationRecord('fake', 0, 'legacy_x', 'point', {'point': [40,40]})
        self.editor.document.add_record(old)
        custom = self.workflow.scheme.copy()
        custom = json.loads(json.dumps(custom))
        custom.update(scheme_id='custom', status='custom')
        custom['objects']['labels'][0]['display_name'] = 'Custom parent'
        self.workflow.scheme_selector.addItem('Custom', custom)
        self.workflow.scheme_selector.setCurrentIndex(1)
        self.assertNotEqual(self.workflow.scheme['scheme_id'], 'custom')
        self.editor.switch_tool('polygon')
        self.editor.tool.mouse_press([20,20])
        self.workflow.apply_button.click()
        self.assertFalse(self.editor.preview)
        self.assertEqual(self.workflow.scheme['scheme_id'], 'custom')
        self.assertEqual(self.editor.document.records.get(old.annotation_id).to_dict(), old.to_dict())
        self.assertIn('Legacy', self.window.annotation_panel.items.item(0).text())
        dialog = CustomSchemeDialog(self.workflow.scheme, self.window)
        self.assertFalse(dialog.table.item(0,0).flags() & Qt.ItemFlag.ItemIsEditable)
        dialog.close()

    def test_layout_languages_ids_and_drawing_target(self):
        self.assertEqual(len(self.workflow.checkboxes), 10)
        self.assertEqual(self.workflow.scheme_group.title(), '标注体系')
        self.assertEqual(self.workflow.quality_group.title(), '判定与备注')
        self.assertTrue(self.window.annotation_dock.isAncestorOf(self.workflow.notes))
        self.assertTrue(self.window.annotation_dock.widget().widgetResizable())
        layer = self.window.layer_panel.active_layer
        for i in range(layer.count()):
            enabled = layer.model().item(i).isEnabled()
            self.assertEqual(enabled, layer.itemData(i) in ('manual','reviewed'))
        layer.setCurrentIndex(layer.findData('reviewed'))
        record = self.polygon()
        self.assertEqual(self.editor.document.record_layers[record.annotation_id], 'reviewed')
        with patch.dict(os.environ, {'DROPLET_VISION_LANGUAGE': 'en_US'}):
            other = MainWindow()
        try:
            self.assertEqual(other.editor.workflow.scheme_group.title(), 'Annotation Scheme')
            self.assertEqual(list(other.editor.workflow.checkboxes), list(self.workflow.checkboxes))
            self.assertEqual(list(other.annotation_panel.taxonomy), list(self.window.annotation_panel.taxonomy))
        finally:
            other.close()

    def test_name_suggestion_rename_history_and_undo(self):
        self.workflow.auto_name.click()
        self.assertEqual(self.workflow.instance_name.text(), 'Parent_01')
        old = self.polygon()
        self.workflow.auto_name.click()
        self.assertEqual(self.workflow.instance_name.text(), 'Parent_02')
        self.workflow.instance_name.setText('Custom name')
        self.workflow.rename_button.click()
        new = self.editor.selected_record()
        self.assertEqual(new.attributes['instance_name'], 'Custom name')
        self.assertEqual(new.geometry, old.geometry)
        self.assertEqual(new.label_id, old.label_id)
        self.assertEqual(new.derived_from, old.annotation_id)
        self.assertEqual(self.editor.document.records.get(old.annotation_id).attributes['instance_name'], 'Parent_01')
        self.editor.undo_stack.undo()
        self.assertEqual(self.editor.document.active_annotation_ids, {old.annotation_id})
        self.editor.undo_stack.redo()
        self.editor.select(new.annotation_id)
        self.workflow.instance_name.clear()
        self.workflow.rename_button.click()
        self.assertEqual(self.editor.selected_record().attributes['instance_name'], '')

    def test_midpoint_click_drag_one_undo_and_display_integrity(self):
        old = self.polygon()
        self.assertEqual(len(self.editor.midpoints), 4)
        self.assertEqual(self.editor.midpoints[-1][1], [20,60])
        for _, _, item in self.editor.midpoints:
            self.assertIsInstance(item, QGraphicsRectItem)
            self.assertTrue(item.flags() & QGraphicsItem.GraphicsItemFlag.ItemIgnoresTransformations)
        self.window.canvas.zoom(2)
        self.window.canvas.horizontalScrollBar().setValue(12)
        count = self.editor.undo_stack.count()
        self.editor.tool.mouse_press([60,20])
        self.editor.tool.mouse_move([65,12])
        self.assertEqual(self.editor.undo_stack.count(), count)
        self.editor.tool.mouse_release([65,12])
        new = self.editor.selected_record()
        self.assertEqual(new.geometry['points'][1], [65,12])
        self.assertEqual(len(self.editor.midpoints), 5)
        self.assertEqual(self.editor.undo_stack.count(), count+1)
        self.editor.undo_stack.undo()
        self.assertEqual(self.editor.document.active_annotation_ids, {old.annotation_id})
        self.editor.undo_stack.redo()
        self.editor.select(new.annotation_id)
        raw = self.window.raw_image.copy()
        for mode in ('raw','photometric_ref90','manual','auto_percentile'):
            self.window.display_panel.set_settings(DisplaySettings(mode=mode))
            self.assertEqual(self.editor.selected_record().geometry, new.geometry)
            np.testing.assert_array_equal(raw, self.window.raw_image)
        self.editor.select(old.annotation_id)
        self.editor.undo_stack.undo()
        self.editor.select(old.annotation_id)
        self.editor.tool.mouse_press([20,60])
        self.editor.tool.mouse_release([20,60])
        self.assertEqual(self.editor.selected_record().geometry['points'][-1], [20,60])

    def test_state_quality_notes_history_navigation_and_save(self):
        boxes = self.workflow.checkboxes
        boxes['nucleation'].trigger()
        first = self.editor.document.frame_state(0)
        boxes['bubble_growth'].trigger()
        second = self.editor.document.frame_state(0)
        self.assertEqual(second.derived_from, first.record_id)
        self.assertEqual(second.state_ids, ('nucleation','bubble_growth'))
        self.workflow.uncertain.click()
        count = len(self.editor.document.frame_state_records)
        self.workflow.notes.setPlainText('Review these adjacent frames')
        self.assertEqual(len(self.editor.document.frame_state_records), count)
        self.workflow.apply_notes.click()
        record = self.editor.document.frame_state(0)
        self.assertTrue(record.uncertain)
        self.assertEqual(record.raw_time64, self.window.current_record.timestamp_time64)
        self.assertEqual(record.relative_timestamp_s, self.window.current_record.timestamp_s)
        self.editor.undo_stack.undo()
        self.assertEqual(self.workflow.notes.toPlainText(), '')
        self.editor.undo_stack.redo()
        self.window.navigate(1000)
        wait_for(lambda: self.window.current_record.frame_index == 1000)
        self.assertFalse(any(box.isChecked() for box in boxes.values()))
        self.assertFalse(self.workflow.uncertain.isChecked())
        self.assertEqual(self.workflow.notes.toPlainText(), '')
        self.window.navigate(0)
        wait_for(lambda: self.window.current_record.frame_index == 0)
        self.assertTrue(boxes['nucleation'].isChecked())
        self.assertEqual(self.workflow.notes.toPlainText(), record.notes)
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)/'annotations.json'
            self.editor.save(path)
            self.assertTrue(self.editor.load(path))
            self.assertEqual(self.editor.document.frame_state(0), record)
        self.assertEqual(len(self.editor.document.records.records()), 0)

    def test_exclusivity_single_undo_and_pending_notes_dirty_guard(self):
        boxes = self.workflow.checkboxes
        boxes['nucleation'].trigger()
        boxes['bubble_growth'].trigger()
        count = self.editor.undo_stack.count()
        boxes['simple_evaporation'].click()
        self.assertEqual(self.editor.undo_stack.count(), count+1)
        self.assertEqual(self.editor.document.frame_state(0).state_ids, ('simple_evaporation',))
        self.editor.undo_stack.undo()
        self.assertEqual(self.editor.document.frame_state(0).state_ids, ('nucleation','bubble_growth'))
        self.editor.undo_stack.redo()
        boxes['burning'].click()
        self.assertFalse(boxes['simple_evaporation'].isChecked())
        self.workflow.notes.setPlainText('unsaved notes')
        with patch.object(QMessageBox, 'warning', return_value=QMessageBox.StandardButton.Cancel):
            self.assertFalse(self.editor.confirm_discard())
        self.assertEqual(self.editor.document.frame_state(0).notes, 'unsaved notes')

    def test_all_jumps_clamp_and_review_speed(self):
        transport = self.window.transport
        for delta in transport.jump_buttons:
            self.window.navigate(1500)
            wait_for(lambda: self.window.current_record.frame_index == 1500)
            transport.jump_buttons[delta].click()
            wait_for(lambda: self.window.current_record.frame_index == 1500+delta)
            self.assertEqual(transport.fps.currentText(), '10')
        self.window.navigate(0)
        wait_for(lambda: self.window.current_record.frame_index == 0)
        transport.jump_buttons[-1000].click()
        wait_for(lambda: self.editor.ready)
        self.assertEqual(self.window.current_record.frame_index, 0)
        transport.fps.setCurrentText('1000')
        self.window.review_clock.now = lambda: 0.0
        self.window.toggle_play()
        self.window.review_clock.now = lambda: 0.001
        self.window._tick()
        wait_for(lambda: self.window.current_record.frame_index == 1)
        self.window.pause()
        transport.jump_buttons[1000].click()
        wait_for(lambda: self.window.current_record.frame_index == 1001)
        self.assertEqual(transport.fps.currentText(), '1000')


@unittest.skipUnless(QT_AVAILABLE and os.environ.get('DROPLET_VISION_LAYOUT_TEST_CINE'), 'Real DHVO Cine not enabled')
class RealWorkflowTests(unittest.TestCase):
    def test_real_roundtrip_raw_export_time_and_source_unchanged(self):
        app = QApplication.instance() or QApplication([])
        path = Path(os.environ['DROPLET_VISION_LAYOUT_TEST_CINE'])
        before = path.stat()
        window = MainWindow()
        try:
            window.open_cine(path)
            wait_for(lambda: window.current_record is not None)
            window.navigate(round((window.metadata.frame_count-1)*.03))
            wait_for(lambda: window.editor.ready)
            editor, workflow = window.editor, window.editor.workflow
            workflow.apply_button.click()
            workflow.auto_name.click()
            for point in ([20,20],[100,20],[100,100],[20,100]):
                editor.tool.mouse_press(point)
            editor.tool.commit()
            editor.switch_tool('select')
            raw_hash = hashlib.sha256(window.raw_image.tobytes()).hexdigest()
            editor.tool.mouse_press([60,20])
            editor.tool.mouse_move([60,30])
            editor.tool.mouse_release([60,30])
            editor.undo_stack.undo()
            editor.undo_stack.redo()
            window.annotation_panel.labels.setCurrentRow(1)
            editor.create_annotation('polygon', {'points': [[40,40],[50,40],[50,50]]})
            workflow.checkboxes['nucleation'].trigger()
            workflow.checkboxes['bubble_growth'].trigger()
            workflow.uncertain.click()
            workflow.notes.setPlainText('Synthetic workflow smoke; not scientific ground truth.')
            workflow.apply_notes.click()
            for mode in ('raw','photometric_ref90'):
                window.display_panel.set_settings(DisplaySettings(mode=mode))
                self.assertEqual(hashlib.sha256(window.raw_image.tobytes()).hexdigest(), raw_hash)
            output = Path('outputs/viewer_smoke/workflow_v1_3')
            output.mkdir(parents=True, exist_ok=True)
            editor.save(output/'synthetic.annotations.json')
            snapshot = editor.document.to_dict()
            index = window.current_record.frame_index
            window.transport.jump_buttons[1000].click()
            wait_for(lambda: window.current_record.frame_index == index+1000)
            window.transport.jump_buttons[-1000].click()
            wait_for(lambda: window.current_record.frame_index == index)
            window.transport.fps.setCurrentText('1000')
            window.review_clock.now = lambda: 0.0
            window.toggle_play()
            window.review_clock.now = lambda: 0.001
            window._tick()
            wait_for(lambda: window.current_record.frame_index == index+1)
            window.pause()
            window.close()
            window = MainWindow()
            window.open_cine(path)
            wait_for(lambda: window.current_record is not None)
            self.assertTrue(window.editor.load(output/'synthetic.annotations.json'))
            self.assertEqual(window.editor.document.to_dict(), snapshot)
            window.navigate(index)
            wait_for(lambda: window.current_record.frame_index == index)
            from droplet_vision.ui.display import export_png
            from PIL import Image
            export_png(window.raw_image, output/'raw_export.png')
            np.testing.assert_array_equal(np.asarray(Image.open(output/'raw_export.png')), window.raw_image)
            (output/'integration_summary.json').write_text(json.dumps({
                'frame_index': index, 'frame_state': window.editor.document.frame_state(index).to_dict(),
                'object_count': len(window.editor.document.active_records(index)),
                'raw_hash_unchanged': True, 'raw_export_equal': True,
                'source_unchanged': (before.st_size,before.st_mtime_ns)==(path.stat().st_size,path.stat().st_mtime_ns)
            }, indent=2), encoding='utf-8')
        finally:
            with patch.object(QMessageBox, 'warning', return_value=QMessageBox.StandardButton.Discard):
                window.close()
        self.assertEqual((before.st_size,before.st_mtime_ns),(path.stat().st_size,path.stat().st_mtime_ns))
