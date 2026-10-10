"""Global support projections, local overrides and session-only list actions."""
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path
from test_ui_main_window import QT_AVAILABLE, wait_for
import test_ui_layout as layout_tests
import test_ui_annotation_queue as queue_tests
from test_support_templates import rod

if QT_AVAILABLE:
    from droplet_vision.ui import i18n
    from droplet_vision.annotations import AnnotationRecord, ViewerSession
    from PySide6.QtCore import Qt


@unittest.skipUnless(QT_AVAILABLE, 'Qt unavailable')
class SupportTemplateUiTests(unittest.TestCase):
    setUpClass = layout_tests.LayoutTests.__dict__['setUpClass']
    close_window = layout_tests.LayoutTests.close_window

    def setUp(self):
        layout_tests.LayoutTests.setUp(self)
        self.panel = self.editor.workflow.support_template
        self.list = self.window.annotation_panel
        self.list.object_buttons['support_structure'].click()

    def create_rods(self):
        for x in (20,50):
            self.assertTrue(self.editor.create_annotation('polygon',
                {'points':[[x,20],[x+5,20],[x+5,150],[x,150]]}))
        self.panel.apply.click()
        return self.editor.document.cine_templates

    def go(self, frame):
        self.window.navigate(frame)
        wait_for(lambda:self.window.current_record.frame_index==frame and self.editor.ready)

    def test_conditional_checkbox_global_projection_and_markers(self):
        self.assertEqual(self.list.object_buttons['support_structure'].text(),'载滴杆')
        self.assertFalse(self.panel.apply.isEnabled())
        for label in ('parent_droplet','internal_cavity_candidate','daughter_droplet'):
            self.list.object_buttons[label].click()
            self.assertFalse(self.panel.apply.isVisible())
        self.list.object_buttons['support_structure'].click()
        self.assertTrue(self.panel.apply.isVisible())
        template=self.create_rods()
        self.assertTrue(template['support_structure']['apply_entire_cine'])
        doc=self.editor.document
        count=len(doc.records.records())
        for frame in (0,20,3200):
            self.go(frame)
            self.assertEqual(len(doc.records.records()),count)
            self.assertEqual(len(self.window.canvas.overlays.by_id),2)
            self.assertTrue(self.panel.apply.isChecked())
        self.assertEqual(self.window.timeline.slider.marked_frames,{0})
        self.panel.apply_current(True)
        self.assertEqual(len(doc.records.records()),count)
        self.panel.apply.click()
        self.assertEqual(len(self.window.canvas.overlays.by_id),0)
        self.assertEqual(len(doc.active_records()),2)
        self.editor.undo()
        self.assertEqual(len(self.window.canvas.overlays.by_id),2)
        self.editor.redo()
        self.assertFalse(self.panel.apply.isChecked())

    def test_visibility_projection_and_records_session_without_data_changes(self):
        self.create_rods();self.go(30)
        doc=self.editor.document
        projection=next(iter(self.editor.projections().values()))
        self.editor.select_from_list(projection.annotation_id)
        before=doc.to_dict()
        self.list.eye_buttons[projection.annotation_id].click()
        self.assertEqual(self.editor.selected_id,projection.annotation_id)
        self.assertNotIn(projection.annotation_id,self.window.canvas.overlays.by_id)
        self.assertFalse(self.editor.handles)
        self.assertEqual(before,doc.to_dict())
        self.assertEqual(self.window.timeline.slider.marked_frames,{0})
        self.assertNotIn('删除标注',[a.text() for a in self.list.context_menu(projection.annotation_id).actions()])
        self.assertIn('Cine 模板',self.list.items.item(0).text())
        self.assertTrue(self.panel.apply.isChecked())
        self.go(40)
        self.assertNotIn(projection.annotation_id,self.window.canvas.overlays.by_id)
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'session.json';self.window.save_session(path)
            loaded=ViewerSession.load(path)
            self.assertIn(projection.annotation_id,loaded.ui_state['hidden_annotation_ids'])
            self.window.session=loaded;self.window.refresh_overlays()
            self.assertNotIn(projection.annotation_id,self.window.canvas.overlays.by_id)
        self.list.eye_buttons[projection.annotation_id].click()
        self.assertIn(projection.annotation_id,self.window.canvas.overlays.by_id)
        manual=rod(doc,40);self.editor.changed();before=doc.to_dict()
        self.list.eye_buttons[manual.annotation_id].click()
        self.assertEqual(before,doc.to_dict())
        self.assertIn(40,self.window.timeline.slider.marked_frames)
        self.assertIn(manual.annotation_id,doc.active_annotation_ids)

    def test_real_row_click_eye_click_and_context_event(self):
        from PySide6.QtTest import QTest
        from PySide6.QtWidgets import QMenu
        from PySide6.QtGui import QContextMenuEvent
        from PySide6.QtCore import QTimer
        self.create_rods();self.go(40)
        projection=next(iter(self.editor.projections().values()))
        self.window.info_dock.widget().ensureWidgetVisible(self.list.items)
        self.app.processEvents()
        item=self.list.items.item(0)
        position=self.list.items.visualItemRect(item).center()
        QTest.mouseClick(self.list.items.viewport(),Qt.MouseButton.LeftButton,pos=position)
        self.assertEqual(self.editor.selected_id,projection.annotation_id)
        QTest.mouseClick(self.list.eye_buttons[projection.annotation_id],Qt.MouseButton.LeftButton)
        self.assertEqual(self.editor.selected_id,projection.annotation_id)
        self.assertNotIn(projection.annotation_id,self.window.canvas.overlays.by_id)
        before=self.editor.hidden_ids()
        opened=[]
        def close_menu():
            menu=self.app.activePopupWidget()
            if isinstance(menu,QMenu):
                opened.extend(a.text() for a in menu.actions())
                menu.close()
        QTimer.singleShot(0,close_menu)
        event=QContextMenuEvent(QContextMenuEvent.Reason.Mouse,position,
                               self.list.items.viewport().mapToGlobal(position))
        self.app.sendEvent(self.list.items.viewport(),event)
        self.assertEqual(opened,['隐藏此模板', '取消全 Cine 应用', '重置本帧位置'])
        self.assertEqual(self.editor.hidden_ids(),before)

    def test_local_override_delete_undo_and_template_isolation(self):
        template=self.create_rods();self.go(40)
        doc=self.editor.document
        source=doc.records.get(template['support_structure']['annotation_ids'][0]).to_dict()
        projection=next(iter(self.editor.projections().values()))
        geometry=deepcopy(projection.geometry);geometry['points'][0][0]+=3
        self.assertTrue(self.editor.edit_annotation(projection.annotation_id,geometry))
        override=doc.support_copies(40)[0]
        self.assertEqual(override.attributes['creation_tool'],'cine_support_template_override')
        self.assertIsNone(override.derived_from)
        self.assertIn(40,self.window.timeline.slider.marked_frames)
        self.assertNotIn(projection.annotation_id,self.window.canvas.overlays.by_id)
        self.assertEqual(doc.records.get(source['annotation_id']).to_dict(),source)
        self.go(60)
        self.assertEqual(self.editor.projections()[projection.annotation_id].geometry,source['geometry'])
        self.go(40)
        action=self.list.context_menu(override.annotation_id).actions()[0]
        self.assertTrue(action.isEnabled());action.trigger()
        self.assertIn(projection.annotation_id,self.window.canvas.overlays.by_id)
        self.assertNotIn(40,self.window.timeline.slider.marked_frames)
        self.assertEqual(doc.records.get(override.annotation_id).geometry,geometry)
        self.editor.undo();self.assertIn(override.annotation_id,doc.active_annotation_ids)
        self.editor.redo();self.assertNotIn(override.annotation_id,doc.active_annotation_ids)
        self.assertEqual(doc.cine_templates,template)

    def test_delete_locked_and_prediction_disabled_language_and_reload(self):
        self.create_rods();self.go(40)
        doc=self.editor.document
        for source,layer in [('model','prediction'),('manual','ground_truth')]:
            record=AnnotationRecord(doc.cine_id,40,'parent_droplet','point',{'point':[5,5]},source=source)
            doc.add_record(record,layer)
            self.editor.changed()
            self.assertFalse(self.list.context_menu(record.annotation_id).actions()[0].isEnabled())
            self.editor.delete_record(record.annotation_id)
            self.assertIn(record.annotation_id,doc.active_annotation_ids)
        projection=next(iter(self.editor.projections()))
        raw=self.window.raw_image.copy();photo=self.window.controller.photometric.to_dict()
        self.window.change_language('en_US')
        self.assertEqual(self.panel.apply.text(),'Apply to entire Cine')
        self.assertTrue(any('Cine template' in self.list.items.item(i).text() for i in range(self.list.items.count())))
        for mode in (self.window.display_panel.show_raw,self.window.display_panel.show_photometric):
            mode();self.assertTrue((self.window.raw_image==raw).all())
        self.assertEqual(self.window.controller.photometric.to_dict(),photo)
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'rods.json';self.editor.save(path)
            expected=doc.to_dict()
            self.window.close_cine();self.window.open_cine('fake.cine')
            wait_for(lambda:self.window.current_record is not None)
            self.assertEqual(self.editor.document.cine_templates,{})
            self.editor.load(path);self.go(80)
            self.assertEqual(self.editor.document.to_dict(),expected)
            self.assertIn(projection,self.window.canvas.overlays.by_id)
            self.assertTrue(self.panel.apply.isChecked())


@unittest.skipUnless(QT_AVAILABLE, 'Qt unavailable')
class QueueTemplateTests(unittest.TestCase):
    setUpClass = queue_tests.QueueUiTests.__dict__['setUpClass']
    setUp = queue_tests.QueueUiTests.setUp
    close = queue_tests.QueueUiTests.close
    open_item = queue_tests.QueueUiTests.open_item

    def test_same_cine_reuses_template_other_cine_has_own_document(self):
        self.open_item(0)
        editor=self.window.editor
        editor.workflow.apply_scheme()
        rod(editor.document,5);editor.changed()
        self.window.annotation_panel.select_label_id('support_structure')
        panel=editor.workflow.support_template;panel.apply.click()
        template=editor.document.cine_templates
        editor.save(editor.default_path())
        self.open_item(1)
        self.assertEqual(editor.document.cine_templates,template)
        self.assertEqual(len(editor.projections()),1)
        self.assertEqual(editor.document.active_records(15),[])
        self.open_item(2)
        self.assertEqual(editor.document.cine_templates,{})
        self.assertFalse(panel.apply.isEnabled())
        self.open_item(1)
        self.assertEqual(editor.document.cine_templates,template)
        self.assertTrue(panel.apply.isChecked())


if __name__ == '__main__':
    unittest.main()
