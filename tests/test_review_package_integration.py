"""Opt-in real Cine export -> PNG-only review -> non-destructive local merge."""
import json
import os
from pathlib import Path
import unittest
from unittest.mock import patch
import numpy as np
from test_review_package import AnnotationDocument, AnnotationRecord, FrameStateRecord, load_scheme
from droplet_vision.cine import CineReader
from droplet_vision.review_package import ReviewPackage, ReviewFrameProvider, merge_review
from droplet_vision.review_package.cine_export import export_cines
from droplet_vision.display.photometric import apply_locked_gain, PhotometricReference

SOURCE = os.environ.get('DROPLET_VISION_LAYOUT_TEST_CINE')


@unittest.skipUnless(SOURCE and Path(SOURCE).is_file(),'Set DROPLET_VISION_LAYOUT_TEST_CINE for real review integration')
class RealReviewTests(unittest.TestCase):
    def test_roundtrip_readonly_review_without_cine(self):
        from PySide6.QtWidgets import QApplication, QMessageBox
        from droplet_vision.ui.main_window import MainWindow
        app = QApplication.instance() or QApplication([])
        root = Path(__file__).resolve().parents[1]
        output = root/'outputs/viewer_smoke/portable_review_v1'
        output.mkdir(parents=True,exist_ok=True)
        source = Path(SOURCE)
        before = (source.stat().st_size,source.stat().st_mtime_ns)
        directory_before = sorted(p.name for p in source.parent.iterdir())
        targets = [966,16098,16739]
        with CineReader(source) as reader:
            meta = reader.metadata
            identity = reader.build_frame_result(0).cine_id
            doc = AnnotationDocument(identity,meta.filename,meta.file_size_bytes,meta.frame_count,meta.width,meta.height)
            doc.scheme = load_scheme()
            for index in targets:
                result = reader.build_frame_result(index)
                record = AnnotationRecord(identity,index,'parent_droplet','polygon',
                    {'points':[[20,20],[80,20],[60,80]]},attributes={'instance_name':'Synthetic_smoke_only',
                    'raw_time64':result.timestamp_time64,'relative_timestamp_s':result.timestamp_s})
                doc.add_record(record)
                state = FrameStateRecord(identity,index,result.timestamp_time64,result.timestamp_s,
                    state_ids=('oscillation_deformation',),uncertain=True,notes='Synthetic software smoke fixture; not scientific Ground Truth')
                doc.add_frame_state(state);doc.activate_frame_state(index,state.record_id)
            raw = {i:reader.read_frame(i).copy() for i in targets}
            time64 = {i:reader.build_frame_result(i).timestamp_time64 for i in targets}
        doc.save(output/'local_base.annotations.json')
        base_value = doc.to_dict()
        package = export_cines([{'path':source,'document':doc,'targets':targets}],doc.scheme,5,'Synthetic smoke fixture')
        original = output/'real_export.dvrpkg';package.save(original)
        package.save(output/'real_export_copy.dvrpkg')
        self.assertEqual(package.summary()['target_frames'],3)
        self.assertEqual(package.summary()['context_frames'],30)
        reopened = ReviewPackage.open(original)
        provider = ReviewFrameProvider(reopened)
        gain = PhotometricReference(**reopened.manifest['photometric'][identity])
        for i in targets:
            np.testing.assert_array_equal(provider.get_frame(identity,i),raw[i])
            np.testing.assert_array_equal(apply_locked_gain(provider.get_frame(identity,i),gain),apply_locked_gain(raw[i],gain))
            self.assertEqual(provider.metadata[identity,i]['raw_time64'],time64[i])
        w = MainWindow()
        try:
            with patch('droplet_vision.ui.cine_controller.CineReader',side_effect=AssertionError('No Cine permitted in review')):
                w.review_manager.normal_controller._reader_factory = lambda *a: self.fail('Cine read in package mode')
                w.review_manager.open(reopened,'Synthetic reviewer')
                first = w.editor.document.active_records(966)[0]
                self.assertTrue(w.editor.edit_annotation(first.annotation_id,{'points':[[22,20],[80,20],[60,80]]}))
                w.editor.undo();w.editor.redo()
                w.navigate(16098)
                w.editor.select(w.editor.document.active_records(16098)[0].annotation_id)
                w.review_manager.decide('object','rejected')
                w.navigate(16739)
                w.annotation_panel.select_label_id('daughter_droplet')
                w.editor.workflow.instance_name.setText('Synthetic_Daughter_01')
                self.assertTrue(w.editor.create_annotation('point',{'point':[110,90]}))
                w.editor.workflow.checkboxes['bubble_growth'].setChecked(True)
                w.review_manager.mark_frame()
                reopened.review['frame_notes'][identity+':16739']='Synthetic review note'
                reviewed = output/'real_reviewed.dvrpkg';reopened.save(reviewed)
            returned = ReviewPackage.open(reviewed)
            merged, conflicts = merge_review(doc,returned)
            self.assertFalse(conflicts)
            self.assertEqual(doc.to_dict(),base_value)
            for record in doc.active_records():
                self.assertIn(record.annotation_id,merged.active_annotation_ids)
                self.assertEqual(record.to_dict(),merged.records.get(record.annotation_id).to_dict())
            merged.save(output/'merged_reviewed.annotations.json')
            self.assertTrue(any(v=='reviewed' for v in merged.record_layers.values()))
        finally:
            with patch.object(QMessageBox,'warning',return_value=QMessageBox.StandardButton.Discard):w.close()
            app.processEvents()
        after = (source.stat().st_size,source.stat().st_mtime_ns)
        self.assertEqual(before,after)
        self.assertEqual(directory_before,sorted(p.name for p in source.parent.iterdir()))
        report = {**package.summary(),'source_filename':source.name,'source_bytes':before[0],
            'source_mtime_ns':before[1],'package_bytes':original.stat().st_size,'reviewed_bytes':reviewed.stat().st_size,
            'source_unchanged':before==after,'source_directory_unchanged':True,'pixel_equality':True,
            'timing_preserved':True,'Cine_reads_in_review_mode':0,'manual_history_unchanged':True,
            'reviewed_layer_import':True,'ground_truth_auto_promoted':False,'gain_used':gain.gain_used}
        (output/'real_integration.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
        print('PORTABLE_REVIEW_REAL',json.dumps(report))
