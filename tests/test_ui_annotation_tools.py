import os
from pathlib import Path
import unittest
from unittest.mock import patch

import numpy as np
from test_ui_main_window import QT_AVAILABLE, FakeReader, wait_for

if QT_AVAILABLE:
    from PySide6.QtCore import QPointF, Qt
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QApplication, QMessageBox
    from droplet_vision.ui.main_window import MainWindow
    from droplet_vision.ui.cine_controller import CineController


class EditorReader(FakeReader):
    def __init__(self, path):
        super().__init__(path)
        self.metadata.width = self.metadata.height = 256
        self.metadata.frame_count = 100

    def read_frame(self, index):
        return np.full((256, 256), 40 + index, dtype=np.uint8)


@unittest.skipUnless(QT_AVAILABLE, 'Optional Qt unavailable')
class AnnotationToolsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.window = MainWindow(Path(__file__).parent / 'fixtures/experimental_taxonomy.json',
                                 controller=CineController(reader_factory=EditorReader))
        self.addCleanup(self.close_window)
        self.window.show()
        self.window.open_cine('fake.cine')
        wait_for(lambda: self.window.current_record is not None)
        self.window.annotation_panel.labels.setCurrentRow(0)
        self.canvas = self.window.canvas
        self.canvas.resetTransform()
        self.editor = self.window.editor

    def close_window(self):
        with patch.object(QMessageBox, 'warning', return_value=QMessageBox.StandardButton.Discard):
            self.window.close()

    def click(self, x, y):
        QTest.mouseClick(self.canvas.viewport(), Qt.MouseButton.LeftButton,
                         pos=self.canvas.mapFromScene(QPointF(x, y)))

    def drag(self, start, end):
        QTest.mousePress(self.canvas.viewport(), Qt.MouseButton.LeftButton,
                         pos=self.canvas.mapFromScene(QPointF(*start)))
        QTest.mouseMove(self.canvas.viewport(), self.canvas.mapFromScene(QPointF(*end)))
        QTest.mouseRelease(self.canvas.viewport(), Qt.MouseButton.LeftButton,
                           pos=self.canvas.mapFromScene(QPointF(*end)))

    def test_point_bbox_mouse_coordinates_and_degenerate_box(self):
        self.editor.actions['point'].trigger()
        self.click(50, 50)
        record = self.editor.document.active_records()[0]
        self.assertEqual(record.geometry, {'point': [50, 50]})
        self.assertEqual(record.label_id, 'experimental_feature_x')
        self.assertEqual(record.attributes['raw_time64'], 0)
        self.assertNotIn('bbox', self.editor.actions)
        self.editor.create_annotation('bbox', {'bbox': [60, 50, 40, 60]})
        self.assertEqual(self.editor.document.active_records()[-1].geometry, {'bbox': [60, 50, 40, 60]})
        self.assertFalse(self.editor.create_annotation('bbox', {'bbox': [10, 10, 0, 0]}))
        self.assertEqual(len(self.editor.document.active_records()), 2)

    def test_polygon_cancel_backspace_enter_and_double_click(self):
        self.editor.actions['polygon'].trigger()
        for point in ((20, 20), (100, 20), (100, 100)):
            self.click(*point)
        QTest.keyClick(self.canvas, Qt.Key.Key_Backspace)
        self.assertEqual(len(self.editor.tool.points), 2)
        self.click(80, 100)
        QTest.keyClick(self.canvas, Qt.Key.Key_Return)  # Close only.
        self.assertFalse(self.editor.document.active_records())
        QTest.keyClick(self.canvas, Qt.Key.Key_Return)  # Explicit confirm.
        self.assertEqual(self.editor.document.active_records()[0].geometry['points'],
                         [[20, 20], [100, 20], [80, 100]])
        self.editor.switch_tool('polygon')
        self.click(10, 10)
        QTest.keyClick(self.canvas, Qt.Key.Key_Escape)
        self.assertEqual(self.editor.tool.points, [])
        self.assertEqual(self.editor.preview, [])
        self.click(40, 40)
        self.click(120, 40)
        QTest.mouseDClick(self.canvas.viewport(), Qt.MouseButton.LeftButton,
                          pos=self.canvas.mapFromScene(QPointF(120, 120)))
        self.assertEqual(len(self.editor.document.active_records()), 1)  # Closed draft only.
        QTest.keyClick(self.canvas, Qt.Key.Key_Return)
        self.assertEqual(len(self.editor.document.active_records()), 2)
        self.assertEqual(len(self.editor.document.active_records()[-1].geometry['points']), 3)

    def test_select_vertex_drag_delete_undo_redo_and_list_sync(self):
        self.editor.create_annotation('polygon', {'points': [[20, 20], [100, 20], [100, 100]]})
        original = self.editor.document.active_records()[0]
        self.editor.switch_tool('select')
        self.editor.select(None)
        self.click(80, 40)
        self.assertEqual(self.editor.selected_id, original.annotation_id)
        self.assertEqual(self.window.annotation_panel.items.currentItem().data(Qt.ItemDataRole.UserRole), original.annotation_id)
        self.drag((100, 100), (120, 110))
        derived = self.editor.document.active_records()[0]
        self.assertEqual(derived.geometry['points'][-1], [120, 110])
        self.assertEqual(derived.derived_from, original.annotation_id)
        self.assertEqual(self.editor.document.records.get(original.annotation_id).geometry, original.geometry)
        self.editor.select(derived.annotation_id)  # select the object, not the vertex, before deactivation
        QTest.keyClick(self.canvas, Qt.Key.Key_Delete)
        self.assertFalse(self.editor.document.active_records())
        QTest.keyClick(self.canvas, Qt.Key.Key_Z, Qt.KeyboardModifier.ControlModifier)
        self.assertEqual(self.editor.document.active_annotation_ids, {derived.annotation_id})
        QTest.keyClick(self.canvas, Qt.Key.Key_Z, Qt.KeyboardModifier.ControlModifier)
        self.assertEqual(self.editor.document.active_annotation_ids, {original.annotation_id})
        QTest.keyClick(self.canvas, Qt.Key.Key_Y, Qt.KeyboardModifier.ControlModifier)
        self.assertEqual(self.editor.document.active_annotation_ids, {derived.annotation_id})
        self.editor.select(None)
        self.window.annotation_panel.items.setCurrentRow(0)
        self.assertEqual(self.editor.selected_id, derived.annotation_id)

    def test_point_and_bbox_handle_editing(self):
        for kind, geometry, start, end, expected in (
            ('point', {'point': [50, 50]}, (50, 50), (60, 70), {'point': [60, 70]}),
            ('bbox', {'bbox': [20, 20, 60, 60]}, (80, 80), (100, 110), {'bbox': [20, 20, 80, 90]})):
            self.editor.create_annotation(kind, geometry)
            before = self.editor.selected_record()
            self.editor.switch_tool('select')
            self.drag(start, end)
            self.assertEqual(self.editor.selected_record().geometry, expected)
            self.assertEqual(self.editor.selected_record().derived_from, before.annotation_id)

    def test_frame_cancel_navigation_and_geometry_restrictions(self):
        self.editor.create_annotation('point', {'point': [50, 50]})
        self.editor.switch_tool('polygon')
        self.click(10, 10)
        self.click(50, 10)
        self.window.navigate(5)
        self.assertFalse(self.editor.preview)
        self.assertIn('cancelled', self.window.statusBar().currentMessage())
        wait_for(lambda: self.window.current_record.frame_index == 5)
        self.editor.create_annotation('point', {'point': [70, 70]})
        self.assertEqual(self.editor.document.annotated_frames(), [0, 5])
        self.editor.annotated_frame(-1)
        wait_for(lambda: self.window.current_record.frame_index == 0)
        self.assertIn('Annotated: 1', self.editor.frame_count_label.text())
        self.assertIn('Annotated frames: 2', self.editor.frame_count_label.text())
        self.editor.annotated_frame(1)
        wait_for(lambda: self.window.current_record.frame_index == 5)
        label = self.window.annotation_panel.selected_label()
        label.allowed_geometry_types = ['point']
        self.editor.update_tools()
        self.assertNotIn('bbox', self.editor.actions)
        self.assertFalse(self.editor.actions['polygon'].isEnabled())
        self.assertFalse(self.editor.create_annotation('bbox', {'bbox': [1, 1, 10, 10]}))
