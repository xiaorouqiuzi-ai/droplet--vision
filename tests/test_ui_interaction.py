"""Interaction v1.4: transient history, local paths and viewport-only transforms."""
import json
import os
import tempfile
from copy import deepcopy
from pathlib import Path
import unittest
from unittest.mock import patch
import numpy as np
import test_ui_annotation_tools as fixture
from test_ui_main_window import QT_AVAILABLE, wait_for

if QT_AVAILABLE:
    from PySide6.QtCore import QPoint, QPointF, Qt, QTimer
    from PySide6.QtGui import QContextMenuEvent, QWheelEvent
    from PySide6.QtWidgets import QApplication, QMessageBox, QGraphicsRectItem, QMenu
    from PySide6.QtTest import QTest
    from droplet_vision.ui.widgets.image_canvas import ImageCanvas
    from droplet_vision.ui import i18n
    from droplet_vision.annotations import ViewerSession
    from droplet_vision.display import DisplaySettings


@unittest.skipUnless(QT_AVAILABLE, 'Qt unavailable')
class DraftTests(unittest.TestCase):
    setUpClass = classmethod(fixture.AnnotationToolsTests.setUpClass.__func__)
    setUp = fixture.AnnotationToolsTests.setUp
    close_window = fixture.AnnotationToolsTests.close_window
    click = fixture.AnnotationToolsTests.click
    drag = fixture.AnnotationToolsTests.drag

    def polygon(self, closed=False):
        self.canvas.set_auto_fit(False)
        self.editor.switch_tool('polygon')
        for xy in ((20,20),(100,20),(100,100),(20,100)):
            self.click(*xy)
        draft = self.editor.tool.draft
        if closed:
            self.click(20,20)
        return draft

    def context_delete(self, point):
        local = self.canvas.mapFromScene(QPointF(*point))
        event = QContextMenuEvent(QContextMenuEvent.Reason.Mouse, local,
                                  self.canvas.viewport().mapToGlobal(local))
        def choose_delete():
            menu = QApplication.activePopupWidget()
            if menu is not None:
                menu.actions()[0].trigger()
                menu.close()
        QTimer.singleShot(0, choose_delete)
        self.canvas.contextMenuEvent(event)

    def test_open_close_handles_animation_and_confirm_only_persistence(self):
        draft = self.polygon()
        self.assertEqual(len(draft.handles), 4)
        self.assertTrue(all(isinstance(h[3], QGraphicsRectItem) for h in draft.handles))
        self.assertEqual(draft.paths[0].pen().style(), Qt.PenStyle.DashLine)
        self.editor.tool.mouse_move([60,80])
        self.assertEqual(draft.paths[0].path().currentPosition(), QPointF(60,80))
        items = list(draft.items)
        phase = draft.paths[0].pen().dashOffset()
        draft.animate()
        self.assertEqual(draft.items, items)
        self.assertNotEqual(draft.paths[0].pen().dashOffset(), phase)
        self.click(20,20)
        self.assertTrue(draft.closed)
        self.assertFalse(self.editor.document.active_records())
        self.assertEqual(len(draft.midpoints), 4)
        self.assertEqual(draft.midpoints[-1][2], [20,60])
        self.assertLess(draft.midpoints[0][3].rect().width(), draft.handles[0][3].rect().width())
        self.assertEqual(draft.midpoints[0][3].brush().style(), Qt.BrushStyle.NoBrush)
        self.editor.tool_settings.confirm_button.click()
        self.assertEqual(len(self.editor.document.active_records()), 1)
        self.assertEqual(len(self.editor.document.records.records()), 1)
        self.assertFalse(draft.timer.isActive())
        item = self.canvas.overlays.items[0]
        self.assertEqual(item.pen().style(), Qt.PenStyle.SolidLine)
        self.assertEqual(self.editor.undo_stack.count(), 1)

    def test_draft_drag_insert_delete_undo_cancel_do_not_touch_document(self):
        before = deepcopy(self.editor.document.to_dict())
        draft = self.polygon()
        self.drag((20,20),(25,25))
        self.assertFalse(draft.closed)
        self.assertEqual(draft.polygons[0][0], [25,25])
        self.editor.undo()
        self.drag((100,20),(110,25))
        self.assertEqual(draft.polygons[0][1], [110,25])
        self.editor.undo()
        self.assertEqual(draft.polygons[0][1], [100,20])
        self.editor.redo()
        self.assertEqual(draft.polygons[0][1], [110,25])
        self.click(20,20)
        midpoint = draft.midpoints[1][2][:]
        self.drag(midpoint,(130,60))
        self.assertEqual(draft.polygons[0][2], [130,60])
        self.assertEqual(len(draft.polygons[0]),5)
        self.editor.undo()
        self.assertEqual(len(draft.polygons[0]),4)
        self.editor.redo()
        self.context_delete((130,60))
        self.assertEqual(len(draft.polygons[0]),4)
        self.editor.undo()
        self.assertEqual(len(draft.polygons[0]),5)
        self.editor.cancel()
        self.assertFalse(draft.timer.isActive())
        self.assertEqual(self.editor.document.to_dict(), before)
        self.assertEqual(self.editor.undo_stack.count(),0)
        self.assertFalse(self.editor.preview)

    def test_minimum_open_delete_and_closed_delete(self):
        self.editor.switch_tool('polygon')
        tool = self.editor.tool
        tool.mouse_press([20,20]); tool.mouse_release([20,20])
        self.assertFalse(tool.commit())
        self.assertFalse(self.editor.document.active_records())
        self.context_delete((20,20))
        self.assertFalse(tool.points)
        for xy in ([20,20],[100,20],[100,100]):
            tool.mouse_press(xy); tool.mouse_release(xy)
        tool.draft.close()
        self.context_delete((100,20))
        self.assertEqual(len(tool.points),3)
        self.assertIn('3',self.window.statusBar().currentMessage())

    def test_draft_zoom_pan_modes_and_persisted_midpoint_one_command(self):
        draft = self.polygon(True)
        self.canvas.zoom(2)
        self.canvas.centerOn(100,100)
        self.drag((100,100),(110,110))
        points = deepcopy(draft.polygons[0])
        self.assertEqual(points[2],[110,110])
        for mode in ('raw','manual','auto_percentile','photometric_ref90'):
            self.window.display_panel.set_settings(DisplaySettings(mode=mode))
            self.assertEqual(draft.polygons[0],points)
        self.editor.tool.commit()
        original = self.editor.selected_record()
        self.assertTrue(all(isinstance(h[2],QGraphicsRectItem) for h in self.editor.handles))
        count = self.editor.undo_stack.count()
        self.drag((60,20),(65,25))
        self.assertEqual(self.editor.undo_stack.count(),count+1)
        revised = self.editor.selected_record()
        self.assertEqual(revised.geometry['points'][1],[65,25])
        self.assertEqual(revised.derived_from,original.annotation_id)
        self.context_delete((65,25))
        self.assertEqual(len(self.editor.selected_record().geometry['points']),4)
        self.assertEqual(self.editor.document.records.get(original.annotation_id).geometry['points'],points)

    def wand(self):
        self.canvas.set_auto_fit(False)
        raw=np.full((256,256),20,np.uint8)
        raw[30:65,30:65]=100
        raw[90:125,90:125]=150
        self.window.raw_image=raw
        self.window.refresh_display()
        self.editor.update_tools()
        self.editor.switch_tool('magic_wand')
        self.click(45,45)
        return raw, self.editor.tool

    def test_wand_shared_draft_parameters_guard_and_compound_confirm(self):
        raw,tool = self.wand()
        before=raw.copy()
        self.assertTrue(tool.draft.closed)
        self.assertTrue(tool.draft.paths)
        self.assertTrue(tool.draft.handles)
        self.editor.wand_panel.tolerance.setValue(9)
        vertex=tool.draft.polygons[0][0][:]
        self.drag(vertex,(vertex[0]+2,vertex[1]+2))
        edited=deepcopy(tool.draft.polygons)
        with patch.object(QMessageBox,'question',return_value=QMessageBox.StandardButton.Cancel) as question:
            self.editor.wand_panel.tolerance.setValue(8)
            question.assert_called_once()
        self.assertEqual(tool.draft.polygons,edited)
        self.assertEqual(self.editor.wand_panel.tolerance.value(),9)
        with patch.object(QMessageBox,'question',return_value=QMessageBox.StandardButton.Yes):
            self.editor.wand_panel.tolerance.setValue(8)
        self.assertFalse(tool.draft.manual_edited)
        self.editor.wand_panel.mode.setCurrentIndex(1)
        self.click(105,105)
        self.assertEqual(len(tool.draft.polygons),2)
        self.assertFalse(self.editor.document.active_records())
        self.assertTrue(tool.commit())
        self.assertEqual(len(self.editor.document.active_records()),2)
        self.assertEqual(self.editor.undo_stack.count(),1)
        self.editor.undo();self.assertFalse(self.editor.document.active_records())
        self.editor.redo();self.assertEqual(len(self.editor.document.active_records()),2)
        np.testing.assert_array_equal(raw,before)

    def test_path_panel_actual_proposed_save_load_and_cine_switch(self):
        panel=self.window.annotation_data_panel
        self.assertIsNone(self.editor.path)
        self.assertIn('Suggested',panel.location_caption.text())
        self.assertEqual(panel.local_path,self.editor.default_path().resolve())
        panel.copy_button.click()
        self.assertEqual(QApplication.clipboard().text(),str(panel.local_path))
        with patch('droplet_vision.ui.panels.annotation_data_panel.QDesktopServices.openUrl') as launch:
            panel.folder_button.click()
            self.assertTrue(launch.call_args.args[0].isLocalFile())
        with tempfile.TemporaryDirectory() as directory:
            first=Path(directory)/'first.json'; second=Path(directory)/'second.json'
            self.editor.create_annotation('point',{'point':[50,50]})
            self.assertEqual(panel.status.text(),'Unsaved changes')
            self.editor.save(first)
            self.assertEqual(panel.status.text(),'Saved')
            self.assertEqual(panel.local_path,first.resolve())
            self.editor.save(second)
            self.assertEqual(panel.filename.text(),'second.json')
            self.assertNotIn(str(Path(directory)),second.read_text(encoding='utf-8'))
            self.editor.load(first)
            self.assertEqual(panel.local_path,first.resolve())
            self.editor.workflow.notes.setPlainText('pending')
            self.assertEqual(panel.status.text(),'Unsaved changes')
            with patch.object(QMessageBox,'warning',return_value=QMessageBox.StandardButton.Discard):
                self.window.open_cine('another.cine')
            wait_for(lambda:self.window.current_record is not None)
            self.assertIsNone(self.editor.path)
            self.assertNotEqual(panel.local_path,first.resolve())

    def test_bbox_retained_without_primary_action_and_puffing_names(self):
        self.assertNotIn('bbox',self.editor.tool_buttons)
        self.assertNotIn('bbox',self.editor.actions)
        self.editor.create_annotation('bbox',{'bbox':[20,20,40,40]})
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'bbox.json';self.editor.save(path);self.editor.load(path)
        self.assertEqual(self.editor.document.active_records()[0].geometry_type,'bbox')
        self.assertIsInstance(self.canvas.overlays.items[0],QGraphicsRectItem)
        try:
            i18n.set_language('zh_CN');self.assertEqual(i18n.tr('Puffing'),'喷发（Puffing）')
            self.editor.workflow._build_states()
            self.assertEqual(self.editor.workflow.checkboxes['puffing'].text(),'喷发（Puffing）')
            # The persisted approved scheme remains byte-for-byte compatible.
            from droplet_vision.annotations.scheme import load_scheme, validate_scheme
            scheme=load_scheme()
            self.assertEqual(next(r['display_name_zh'] for r in scheme['frame_states']['states']
                                  if r['state_id']=='puffing'),'Puffing')
            self.assertEqual(validate_scheme(scheme),scheme)
            i18n.set_language('en_US');self.assertEqual(i18n.tr('Puffing'),'Puffing')
            self.editor.workflow._build_states()
            self.assertEqual(self.editor.workflow.checkboxes['puffing'].text(),'Puffing')
        finally:
            i18n.set_language('en_US')

    def test_session_autofit_false_restored_old_session_defaults_on(self):
        self.canvas.zoom(2)
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'session.json'
            self.window.save_session(path)
            session=ViewerSession.load(path)
            self.assertFalse(session.ui_state['auto_fit_to_view'])
            self.window.open_cine('fake.cine',session)
            wait_for(lambda:self.window.current_record is not None)
            self.assertFalse(self.canvas.auto_fit_enabled)
            session.ui_state.pop('auto_fit_to_view')
            self.window.open_cine('fake.cine',session)
            wait_for(lambda:self.window.current_record is not None)
            self.assertTrue(self.canvas.auto_fit_enabled)

    def test_fit_shortcut_checkbox_resize_and_navigation_do_not_change_geometry(self):
        draft=self.polygon(True)
        points=deepcopy(draft.polygons)
        self.canvas.zoom(2)
        self.assertFalse(self.window.display_panel.auto_fit.isChecked())
        QTest.keyClick(self.canvas,Qt.Key.Key_F)
        self.assertTrue(self.window.display_panel.auto_fit.isChecked())
        self.assertTrue(self.canvas.auto_fit_enabled)
        self.assertEqual(draft.polygons,points)
        self.editor.tool.commit()
        record=self.editor.selected_record()
        self.canvas.zoom(1.4)
        scale=self.canvas.transform().m11()
        self.window.navigate(5)
        wait_for(lambda:self.window.current_record.frame_index==5)
        self.assertEqual(self.canvas.transform().m11(),scale)
        self.assertEqual(self.editor.document.records.get(record.annotation_id).geometry['points'],points[0])


@unittest.skipUnless(QT_AVAILABLE, 'Qt unavailable')
class AutoFitTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app=QApplication.instance() or QApplication([])

    def test_high_resolution_resize_manual_wheel_and_frame_integrity(self):
        canvas=ImageCanvas();self.addCleanup(canvas.close)
        canvas.resize(800,600);canvas.show()
        raw=np.arange(256*256,dtype=np.uint8).reshape(256,256);before=raw.copy()
        canvas.set_image(raw);QTest.qWait(80)
        first=canvas.transform().m11()
        self.assertTrue(canvas.auto_fit_enabled);self.assertGreater(first,2)
        canvas.resize(2400,1400);QTest.qWait(120)
        large=canvas.transform().m11();self.assertGreater(large,first*2)
        self.assertAlmostEqual(large,canvas.transform().m22())
        canvas.resize(800,600);QTest.qWait(120)
        self.assertLess(canvas.transform().m11(),large)
        at=QPointF(150,150)
        event=QWheelEvent(at,at, QPoint(),
                          QPoint(0,120),
                          Qt.MouseButton.NoButton,Qt.KeyboardModifier.NoModifier,
                          Qt.ScrollPhase.NoScrollPhase,False)
        canvas.wheelEvent(event)
        self.assertFalse(canvas.auto_fit_enabled)
        scale=canvas.transform().m11()
        canvas.resize(1500,1000);QTest.qWait(120)
        self.assertEqual(canvas.transform().m11(),scale)
        canvas.set_image(raw+1)
        self.assertEqual(canvas.transform().m11(),scale)
        canvas.fit_image()
        self.assertTrue(canvas.auto_fit_enabled)
        self.assertGreater(canvas.transform().m11(),scale)
        self.assertEqual(canvas.image_item.boundingRect().width(),256)
        self.assertEqual(canvas.sceneRect().width(),256)
        np.testing.assert_array_equal(raw,before)


@unittest.skipUnless(QT_AVAILABLE and os.environ.get('DROPLET_VISION_LAYOUT_TEST_CINE'), 'Real Cine not enabled')
class RealDraftTests(unittest.TestCase):
    def test_real_draft_wand_persistence_raw_export_and_time(self):
        from droplet_vision.ui.main_window import MainWindow
        from droplet_vision.annotations import AnnotationDocument
        from PIL import Image
        app=QApplication.instance() or QApplication([])
        source=Path(os.environ['DROPLET_VISION_LAYOUT_TEST_CINE'])
        before=source.stat()
        window=MainWindow(Path(__file__).parent/'fixtures/experimental_taxonomy.json')
        try:
            window.open_cine(source)
            wait_for(lambda:window.current_record is not None)
            window.annotation_panel.labels.setCurrentRow(0)
            raw=window.raw_image.copy()
            time64=window.current_record.timestamp_time64
            editor=window.editor
            editor.switch_tool('polygon')
            for xy in ((20,20),(100,20),(100,100),(20,100)):
                editor.tool.mouse_press(xy);editor.tool.mouse_release(xy)
            editor.tool.mouse_press((20,20));editor.tool.mouse_release((20,20))
            self.assertFalse(editor.document.active_records())
            editor.tool.mouse_press((100,100));editor.tool.mouse_release((110,110))
            self.assertTrue(editor.tool.commit())
            editor.switch_tool('magic_wand')
            # Probe a small deterministic grid for a geometrically supported region;
            # these are test seeds, never a classifier or physical annotation.
            for x,y in ((.29,.20),(.4,.4),(.6,.3),(.3,.6),(.5,.5)):
                editor.tool.mouse_press((x*(raw.shape[1]-1),y*(raw.shape[0]-1)))
                if editor.tool.valid:
                    break
            self.assertTrue(editor.tool.valid)
            d=editor.tool.draft
            self.assertTrue(d.closed)
            points=deepcopy(d.polygons)
            for mode in ('raw','photometric_ref90','manual','auto_percentile'):
                window.display_panel.set_settings(DisplaySettings(mode=mode))
                self.assertEqual(d.polygons,points)
                np.testing.assert_array_equal(window.raw_image,raw)
            self.assertTrue(editor.tool.commit())
            expected=[r.to_dict() for r in editor.document.active_records()]
            with tempfile.TemporaryDirectory() as directory:
                path=Path(directory)/'draft.json'
                editor.save(path)
                restored=AnnotationDocument.load(path)
                self.assertEqual([r.to_dict() for r in restored.active_records()],expected)
                window.export_frame(Path(directory)/'raw.png')
                with Image.open(Path(directory)/'raw.png') as image:
                    np.testing.assert_array_equal(np.asarray(image),raw)
            self.assertTrue(all(r['attributes']['raw_time64']==time64 for r in expected))
            np.testing.assert_array_equal(window.controller.cache.get(0),raw)
        finally:
            with patch.object(QMessageBox,'warning',return_value=QMessageBox.StandardButton.Discard):
                window.close()
        after=source.stat()
        self.assertEqual((before.st_size,before.st_mtime_ns),(after.st_size,after.st_mtime_ns))
