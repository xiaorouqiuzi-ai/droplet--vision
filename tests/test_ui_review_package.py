import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
import tempfile
from pathlib import Path
import unittest
from unittest.mock import patch
from types import SimpleNamespace
import numpy as np
from test_review_package import fixture
from PySide6.QtWidgets import QApplication, QMessageBox, QDialog
from PySide6.QtCore import QSettings
from droplet_vision.ui.main_window import MainWindow
from droplet_vision.ui.review_package import ExportReviewDialog, ConflictDialog
from droplet_vision.ui import i18n
from droplet_vision.review_package import ReviewPackage, export_package, review_decision
from droplet_vision.annotations import AnnotationDocument
from droplet_vision.schema import FrameResult


class ReviewUITests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        store = QSettings(str(Path(self.tmp.name)/'settings.ini'),QSettings.Format.IniFormat)
        p = patch.object(i18n,'preferences',return_value=store);p.start();self.addCleanup(p.stop)
        self.window = MainWindow()
        self.addCleanup(self.cleanup_window)

    def cleanup_window(self):
        with patch.object(QMessageBox,'warning',return_value=QMessageBox.StandardButton.Discard):
            self.window.close()
        self.app.processEvents()

    def open_fixture(self):
        doc,record,state,pixels,package = fixture()
        # Opening a bundle must never open a Cine, even when no Cine exists locally.
        with patch.object(self.window.review_manager.normal_controller,'_reader_factory',side_effect=AssertionError('Cine access')):
            self.assertTrue(self.window.review_manager.open(package,'Reviewer test'))
        return doc,record,state,pixels,package

    def test_menu_order_live_languages_and_dialog_defaults(self):
        for language in ('en_US','zh_CN','en_US'):
            self.window.change_language(language)
            self.assertEqual([a.text() for a in self.window.menuBar().actions()],
                [i18n.tr(k) for k in ('File','Annotation','Queue','View','Model','Settings','Help')])
        dialog = ExportReviewDialog(self.window)
        self.assertEqual(dialog.context.value(),5)
        self.assertEqual(dialog.context.maximum(),100)
        self.assertEqual(dialog.selection.count(),3)

    def test_sparse_navigation_title_timing_and_snapshot(self):
        _,record,_,pixels,package = self.open_fixture()
        w = self.window;w.change_language('en_US')
        self.assertIn('Portable Review Mode',w.windowTitle())
        self.assertEqual(w.current_record.frame_index,10)
        self.assertEqual(w.current_record.timestamp_time64,1234567890123456799)
        np.testing.assert_array_equal(w.raw_image,pixels)
        self.assertIn(record.annotation_id,w.canvas.overlays.by_id)
        w.review_manager.adjacent(1,True);self.assertEqual(w.current_record.frame_index,14)
        w.step(1);self.assertEqual(w.current_record.frame_index,15)
        w.navigate(25);self.assertEqual(w.current_record.frame_index,15)
        self.assertIn('not included',w.statusBar().currentMessage())
        self.assertEqual(w.timeline.slider.target_frames,{10,14})
        self.assertFalse(w.display_panel.recalculate_button.isEnabled())
        self.assertFalse(w.editor.workflow.scheme_group.isEnabled())

    def test_edit_reject_undo_state_save_reopen_raw_export(self):
        _,record,state,pixels,package = self.open_fixture()
        w=self.window;e=w.editor
        self.assertTrue(e.edit_annotation(record.annotation_id,{'points':[[4,4],[15,3],[15,15]]}))
        derived=e.selected_record()
        self.assertEqual(derived.derived_from,record.annotation_id)
        self.assertEqual(derived.attributes['review_origin'],'review_package')
        w.review_manager.decide('object','rejected')
        self.assertNotIn(derived.annotation_id,e.document.active_annotation_ids)
        e.undo();self.assertIn(derived.annotation_id,e.document.active_annotation_ids)
        e.redo();self.assertNotIn(derived.annotation_id,e.document.active_annotation_ids)
        e.workflow.checkboxes['bubble_growth'].setChecked(True)
        self.assertIn('bubble_growth',e.document.frame_state(10).state_ids)
        self.assertIn(e.document.frame_state(10).record_id,package.review['record_provenance'])
        w.review_manager.mark_frame()
        package.review['frame_notes']['synthetic:10']='review note'
        path=Path(self.tmp.name)/'reviewed.dvrpkg';package.save(path)
        opened=ReviewPackage.open(path)
        self.assertEqual(opened.review['frame_notes']['synthetic:10'],'review note')
        self.assertEqual(opened.documents['synthetic'].records.get(record.annotation_id).to_dict(),record.to_dict())
        from PIL import Image
        raw=Path(self.tmp.name)/'raw.png';w.export_frame(raw)
        np.testing.assert_array_equal(np.array(Image.open(raw)),pixels)

    def test_cancel_blocks_exit_and_cine_switch(self):
        self.open_fixture()
        with patch.object(QMessageBox,'warning',return_value=QMessageBox.StandardButton.Cancel):
            self.assertFalse(self.window.close_cine())
            self.assertFalse(self.window.open_cine('unavailable.cine'))
        self.assertTrue(self.window.review_manager.active)

    def test_conflict_dialog_requires_explicit_selection(self):
        dialog=ConflictDialog([{'conflict_id':'object:A','frame_index':1,'base':{},'local':[],'reviewer':{}}],self.window)
        self.assertIsNone(dialog.choices['object:A'].currentData())
        with patch.object(QMessageBox,'warning') as warning:
            dialog.accept_checked();warning.assert_called_once()
        self.assertNotEqual(dialog.result(),QDialog.DialogCode.Accepted)
        dialog.choices['object:A'].setCurrentIndex(3)
        dialog.accept_checked();self.assertEqual(dialog.result(),QDialog.DialogCode.Accepted)

    def test_queue_status_filter_grouping_and_no_progress_mutation(self):
        doc,_,_,_,_ = fixture()
        root = Path(self.tmp.name)
        doc.save(root/'annotations.json')
        items = [SimpleNamespace(status=status,relative_cine_path='sample.cine',
            annotation_document='annotations.json',cine_filename='sample.cine',
            frame_index=index,item_id=str(index)) for index,status in
            [(10,'DONE'),(14,'NEEDS_REVIEW'),(20,'PENDING')]]
        manager = self.window.queue_manager
        manager.queue = SimpleNamespace(items=items)
        manager.root,manager.path = root,root/'queue.json'
        requests = self.window.review_manager.export_requests('queue',['DONE','NEEDS_REVIEW'])
        self.assertEqual(len(requests),1)
        self.assertEqual(requests[0]['targets'],[10,14])
        self.assertEqual(requests[0]['queue_item_ids'],{10:['10'],14:['14']})
        self.assertEqual([i.status for i in items],['DONE','NEEDS_REVIEW','PENDING'])
        manager.queue = None

    def test_multi_cine_keeps_unsaved_review_and_package_path(self):
        doc,_,_,pixels,_ = fixture()
        second = AnnotationDocument('second','second.cine',123,30,32,32)
        second.scheme = doc.scheme
        package = export_package([{'document':d,'targets':[10], 'get_frame':lambda i:pixels,
            'get_metadata':lambda i,c=d.cine_id:FrameResult(c,i)} for d in (doc,second)],doc.scheme,0)
        path = Path(self.tmp.name)/'multi.dvrpkg';package.save(path)
        self.window.review_manager.open(package,'Tester')
        first = self.window.editor.document.active_records(10)[0]
        self.window.editor.edit_annotation(first.annotation_id,{'points':[[4,4],[15,3],[15,15]]})
        derived = self.window.editor.selected_record().annotation_id
        self.window.review_manager.switch_cine('second')
        self.window.review_manager.switch_cine('synthetic')
        self.assertIn(derived,self.window.editor.document.active_annotation_ids)
        self.assertTrue(package.dirty)
        self.assertEqual(self.window.annotation_data_panel.local_path,path)

    def test_save_dialog_and_import_reviewed_preserve_local_manual(self):
        doc,record,_,_,package = self.open_fixture()
        reviewed_id = review_decision(package,'synthetic','object',record.annotation_id,'accepted')
        path = Path(self.tmp.name)/'returned.dvrpkg'
        with patch('droplet_vision.ui.review_package.QFileDialog.getSaveFileName',return_value=(str(path),'')) as dialog:
            self.assertTrue(self.window.review_manager.save_dialog())
        default = Path(dialog.call_args.args[2])
        self.assertTrue(default.is_absolute());self.assertTrue(default.parent.is_dir())
        self.window.review_manager.leave()
        self.window.editor.document = doc
        with patch('droplet_vision.ui.review_package.QFileDialog.getOpenFileName',return_value=(str(path),'')), patch.object(self.window,'_error') as error:
            self.window.review_manager.import_dialog()
            error.assert_not_called()
        merged = self.window.editor.document
        self.assertIn(record.annotation_id,merged.active_annotation_ids)
        self.assertEqual(merged.record_layers[reviewed_id],'reviewed')
        self.assertEqual(merged.records.get(record.annotation_id).to_dict(),record.to_dict())

    def test_edit_after_explicit_complete_returns_to_in_review(self):
        _,record,_,_,package = self.open_fixture()
        self.window.editor.edit_annotation(record.annotation_id,{'points':[[4,4],[15,3],[15,15]]})
        with patch.object(QMessageBox,'question',return_value=QMessageBox.StandardButton.Yes):
            self.window.review_manager.complete()
        self.assertEqual(package.manifest['package_status'],'reviewed')
        self.window.editor.undo()
        self.assertEqual(package.manifest['package_status'],'in_review')


if __name__=='__main__':unittest.main()
