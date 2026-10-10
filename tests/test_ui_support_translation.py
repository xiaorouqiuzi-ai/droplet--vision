"""Raw-coordinate group handle, one-command edits and sparse persistence."""
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch
import numpy as np
from test_ui_main_window import QT_AVAILABLE, wait_for
import test_ui_layout as layout_tests
from PySide6.QtCore import Qt, QPointF
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QGraphicsItem, QMessageBox
from droplet_vision.annotations import AnnotationDocument
from droplet_vision.annotations.support_translation import translated


@unittest.skipUnless(QT_AVAILABLE,'Qt unavailable')
class SupportTranslationUITests(unittest.TestCase):
    setUpClass=layout_tests.LayoutTests.__dict__['setUpClass']
    close_window=layout_tests.LayoutTests.close_window

    def setUp(self):
        layout_tests.LayoutTests.setUp(self)
        self.window.annotation_panel.select_label_id('support_structure')
        for x in (20,50):
            self.editor.create_annotation('polygon',{'points':[[x,20],[x+5,20],[x+5,150],[x,150]]})
        self.editor.workflow.support_template.apply.click()
        self.doc=self.editor.document
        self.sources=[r.to_dict() for r in self.doc.active_records()]
        self.go(200)
        self.editor.switch_tool('select')
        self.move=self.editor.support_move

    def go(self,frame):
        self.window.navigate(frame)
        wait_for(lambda:self.window.current_record.frame_index==frame and self.editor.ready)

    def drag(self,dx,dy):
        self.editor.refresh_selection()
        point=self.move.item.pos()
        start=(point.x(),point.y())
        self.editor.tool.mouse_press(start)
        self.assertIsNotNone(self.move.drag)
        self.editor.tool.mouse_move((start[0]+dx,start[1]+dy))
        self.editor.tool.mouse_release((start[0]+dx,start[1]+dy))

    def test_handle_preview_one_command_repeated_drag_reset_and_visibility(self):
        self.assertEqual(self.move.item.pos(),QPointF(37.5,85))
        self.assertTrue(self.move.item.flags() & QGraphicsItem.GraphicsItemFlag.ItemIgnoresTransformations)
        before=self.doc.to_dict();count=self.editor.undo_stack.count()
        self.editor.tool.mouse_press((37.5,85))
        self.editor.tool.mouse_move((39.5,84))
        self.assertEqual(self.doc.to_dict(),before)
        self.assertEqual(self.editor.undo_stack.count(),count)
        for record in self.move.group():
            self.assertEqual(self.window.canvas.overlays.by_id[record.annotation_id].pos(),QPointF(2,-1))
        self.editor.tool.mouse_release((39.5,84))
        self.assertEqual(self.doc.support_translation(200),{'dx':2,'dy':-1})
        self.assertEqual(self.editor.undo_stack.count(),count+1)
        self.assertEqual(len(self.doc.records.records()),2)
        self.assertEqual(self.window.timeline.slider.marked_frames,{0,200})
        self.drag(1,-.5)
        self.assertEqual(self.doc.support_translation(200),{'dx':3,'dy':-1.5})
        self.editor.undo();self.assertEqual(self.doc.support_translation(200),{'dx':2,'dy':-1})
        self.editor.redo();self.assertEqual(self.doc.support_translation(200),{'dx':3,'dy':-1.5})
        self.move.reset_button.click()
        self.assertNotIn('frame_overrides',self.doc.cine_templates['support_structure'])
        self.assertEqual(self.window.timeline.slider.marked_frames,{0})
        self.editor.undo();self.assertEqual(self.doc.support_translation(200),{'dx':3,'dy':-1.5})
        key=next(iter(self.editor.projections()))
        self.editor.set_record_visible(key,False)
        self.assertIsNone(self.move.item)
        self.assertIn(200,self.window.timeline.slider.marked_frames)
        self.editor.set_record_visible(key,True)
        self.assertIsNotNone(self.move.item)
        self.editor.select(None)
        self.window.annotation_panel.select_label_id('parent_droplet');self.editor.switch_tool('select')
        self.assertIsNone(self.move.item)
        self.window.annotation_panel.select_label_id('support_structure')
        self.assertIsNone(self.move.item)  # Drawing tool, not Select.

    def test_materialization_consumes_translation_and_local_group_move(self):
        self.drag(2,-1)
        group=self.move.group()
        original=[deepcopy(r.geometry) for r in group]
        self.editor.select(group[0].annotation_id)
        geometry=deepcopy(group[0].geometry);geometry['points'][0][0]+=1
        count=self.editor.undo_stack.count()
        self.assertTrue(self.editor.edit_annotation(group[0].annotation_id,geometry))
        self.assertEqual(self.editor.undo_stack.count(),count+1)
        self.assertEqual(self.doc.support_translation(200),{'dx':0,'dy':0})
        copies=self.doc.support_copies(200)
        self.assertEqual(len(copies),2)
        self.assertEqual(copies[0].geometry,geometry)
        self.assertEqual(copies[1].geometry,original[1])
        self.assertEqual(self.editor.projections(),{})
        self.editor.undo()
        self.assertEqual(self.doc.support_translation(200),{'dx':2,'dy':-1})
        self.assertEqual(len(self.editor.projections()),2)
        self.editor.redo()
        before={r.annotation_id:r.to_dict() for r in copies}
        self.drag(3,4)
        moved=self.doc.support_copies(200)
        for prior,record in zip(copies,moved):
            self.assertEqual(record.geometry,translated(prior.geometry,{'dx':3,'dy':4}))
            self.assertEqual(record.derived_from,prior.annotation_id)
            self.assertEqual(self.doc.records.get(prior.annotation_id).to_dict(),before[prior.annotation_id])
        self.assertEqual(self.doc.support_translation(200),{'dx':0,'dy':0})
        for record in list(moved): self.editor.delete_record(record.annotation_id)
        self.assertEqual([r.geometry for r in self.move.group()],[row['geometry'] for row in self.sources])
        self.assertNotIn(200,self.window.timeline.slider.marked_frames)
        self.assertEqual([self.doc.records.get(row['annotation_id']).to_dict() for row in self.sources],self.sources)

    def test_source_frame_cancel_boundary_clamp_and_save_reload(self):
        self.go(0)
        self.editor.select(self.sources[0]['annotation_id'])
        self.drag(-2.4,1.7)
        self.assertIn('模板来源帧',self.window.statusBar().currentMessage())
        self.assertEqual(len(self.doc.records.records()),2)
        self.assertEqual(len(self.editor.projections()),2)
        self.assertTrue(self.editor.selected_id.startswith('cine-template:'))
        self.assertEqual(self.editor.handles[0][1],self.editor.selected_record().geometry['points'][0])
        self.move.reset_button.click()
        self.assertEqual(self.editor.selected_id,self.sources[0]['annotation_id'])
        self.editor.undo()
        self.assertTrue(self.editor.selected_id.startswith('cine-template:'))
        self.assertEqual([self.doc.records.get(row['annotation_id']).to_dict() for row in self.sources],self.sources)
        self.go(100)
        self.drag(1,2)
        self.go(300)
        before=self.doc.to_dict();point=self.move.item.pos()
        self.editor.tool.mouse_press((point.x(),point.y()))
        self.editor.tool.mouse_move((point.x()+3,point.y()+3))
        self.editor.cancel()
        self.assertEqual(self.doc.to_dict(),before)
        self.drag(-100,-100)
        self.assertEqual(self.doc.support_translation(300),{'dx':-20,'dy':-20})
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'rods.json';self.editor.save(path)
            self.assertEqual(AnnotationDocument.load(path).to_dict(),self.doc.to_dict())
            self.window.close_cine();self.window.open_cine('fake.cine')
            wait_for(lambda:self.window.current_record is not None)
            self.editor.load(path);self.go(100)
            self.assertEqual(self.editor.document.support_translation(100),{'dx':1,'dy':2})
            self.assertEqual(len(self.editor.document.records.records()),2)

    def test_zoom_pan_mouse_drag_and_display_raw_integrity_live_language(self):
        canvas=self.window.canvas
        raw=self.window.raw_image.copy();time64=self.window.current_record.timestamp_time64
        photo=self.window.controller.photometric.to_dict()
        canvas.set_auto_fit(False);canvas.resetTransform();canvas.zoom(2)
        canvas.horizontalScrollBar().setValue(canvas.horizontalScrollBar().value()+13)
        canvas.verticalScrollBar().setValue(canvas.verticalScrollBar().value()+17)
        point=self.move.item.pos()
        start=canvas.mapFromScene(point);end=canvas.mapFromScene(point+QPointF(2,-1))
        delta=canvas.mapToScene(end)-canvas.mapToScene(start)
        QTest.mousePress(canvas.viewport(),Qt.MouseButton.LeftButton,pos=start)
        QTest.mouseMove(canvas.viewport(),end)
        QTest.mouseRelease(canvas.viewport(),Qt.MouseButton.LeftButton,pos=end)
        offset=self.doc.support_translation(200)
        self.assertAlmostEqual(offset['dx'],delta.x());self.assertAlmostEqual(offset['dy'],delta.y())
        for show in (self.window.display_panel.show_raw,self.window.display_panel.show_photometric):
            show();np.testing.assert_array_equal(self.window.raw_image,raw)
        self.assertEqual(self.window.current_record.timestamp_time64,time64)
        self.assertEqual(self.window.controller.photometric.to_dict(),photo)
        before=self.doc.to_dict()
        self.window.change_language('en_US')
        self.assertEqual(self.move.reset_button.text(),'Reset frame position')
        self.assertIn('Frame offset',self.move.offset_label.text())
        self.assertEqual(self.move.item.toolTip(),'Drag to translate the support rod for this frame')
        self.assertEqual(self.doc.to_dict(),before)

    def test_review_materialized_group_move_creates_reviewed_candidates(self):
        from droplet_vision.review_package import export_package,merge_review
        from droplet_vision.schema import FrameResult
        self.drag(2,-1)
        canonical=self.doc
        canonical._saved_revision=canonical._revision
        source={'document':canonical,'targets':[200],
                'get_frame':lambda i:np.full((256,256),40,np.uint8),
                'get_metadata':lambda i:FrameResult(canonical.cine_id,i)}
        package=export_package([source],canonical.scheme,context=0)
        self.assertTrue(self.window.review_manager.open(package,'Synthetic Reviewer'))
        self.editor.switch_tool('select')
        self.window.annotation_panel.select_label_id('support_structure');self.editor.switch_tool('select')
        self.assertIsNotNone(self.move.item)
        before=canonical.to_dict()
        self.drag(1,1)
        result,conflicts=merge_review(canonical,package)
        self.assertEqual(conflicts,[])
        self.assertEqual(canonical.to_dict(),before)
        self.assertEqual(result.cine_templates,canonical.cine_templates)
        candidates=result.support_copies(200)
        self.assertEqual(len(candidates),2)
        self.assertTrue(all(result.record_layers[r.annotation_id]=='reviewed' for r in candidates))
        self.assertTrue(all(r.attributes['creation_tool']=='cine_support_template_override' for r in candidates))


if __name__=='__main__': unittest.main()
