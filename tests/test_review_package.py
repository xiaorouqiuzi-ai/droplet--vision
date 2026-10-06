"""Transport, safety, immutable review and three-way merge contracts."""
import io
import json
import os
from pathlib import Path
import shutil
import tempfile
import unittest
import sys
from unittest.mock import patch
import zipfile

import numpy as np
from PIL import Image
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from droplet_vision.annotations import AnnotationDocument, AnnotationRecord
from droplet_vision.annotations.frame_state import FrameStateRecord
from droplet_vision.annotations.scheme import load_scheme
from droplet_vision.schema import FrameResult, TimingStatus
from droplet_vision.display.photometric import estimate_reference, load_photometric_preset
from droplet_vision.review_package import ReviewPackage, ReviewFrameProvider, export_package, context_frames, merge_review, review_decision
from droplet_vision.review_package.bundle import encode, digest
from droplet_vision.review_package.bundle import snapshot


def fixture():
    doc = AnnotationDocument('synthetic','sample.cine',123456,30,32,32)
    doc.scheme = load_scheme()
    record = AnnotationRecord(doc.cine_id,10,'parent_droplet','polygon',{'points':[[3,3],[15,3],[15,15]]})
    doc.add_record(record)
    state = FrameStateRecord(doc.cine_id,10,1234567890123456789,.123,state_ids=('nucleation',),notes='inspect')
    doc.add_frame_state(state)
    doc.activate_frame_state(10,state.record_id)
    pixels = np.arange(1024,dtype=np.uint8).reshape(32,32)
    photo = estimate_reference(pixels,30,load_photometric_preset()).to_dict()
    source = {'document':doc,'targets':[10,14],'get_frame':lambda i:pixels.copy(),
              'get_metadata':lambda i:FrameResult(doc.cine_id,i,timestamp_time64=1234567890123456789+i,
                  timestamp_s=i*.00123,timing_status=TimingStatus.TIMING_MISMATCH_UNRESOLVED),'photometric':photo}
    package = export_package([source],doc.scheme,context=5)
    return doc,record,state,pixels,package


class ReviewPackageTests(unittest.TestCase):
    def test_snapshot_excludes_model_only_state_but_keeps_review_ancestry(self):
        doc,_,_,_,_ = fixture()
        model = FrameStateRecord('synthetic',14,state_ids=('burning',),source='model')
        doc.add_frame_state(model);doc.activate_frame_state(14,model.record_id)
        self.assertIsNone(snapshot(doc,{10,14}).frame_state(14))
        human = FrameStateRecord('synthetic',14,state_ids=('burning',),derived_from=model.record_id,review_status='edited')
        doc.add_frame_state(human);doc.activate_frame_state(14,human.record_id)
        exported = snapshot(doc,{14})
        self.assertEqual({r.record_id for r in exported.frame_state_records},{model.record_id,human.record_id})

    def test_context_clamp_dedup_and_roles(self):
        result = context_frames([0,4],8,5)
        self.assertEqual(len(result),8)
        self.assertEqual([i for i,r in result.items() if r=='target'],[0,4])
        with self.assertRaises(ValueError): context_frames([0],8,101)

    def test_roundtrip_zip_folder_portable_and_raw(self):
        doc,record,state,pixels,pkg = fixture()
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)/'review.dvrpkg'
            pkg.save(path)
            self.assertFalse(pkg.dirty)
            loaded = ReviewPackage.open(path)
            loaded.save(Path(tmp)/'unpacked',folder=True)
            relocated = Path(tmp)/'relocated'
            shutil.move(str(Path(tmp)/'unpacked'),relocated)
            opened = ReviewPackage.open(relocated)
            provider = ReviewFrameProvider(opened)
            self.assertEqual(provider.available('synthetic'),list(range(5,20)))
            self.assertEqual(provider.available('synthetic',True),[10,14])
            self.assertEqual(provider.adjacent('synthetic',10,1,True),14)
            self.assertEqual(provider.adjacent('synthetic',10,-1),9)
            with self.assertRaises(KeyError): provider.get_frame('synthetic',22)
            image = provider.get_frame('synthetic',10)
            np.testing.assert_array_equal(image,pixels)
            self.assertFalse(image.flags.writeable)
            row = provider.metadata['synthetic',10]
            self.assertEqual(row['raw_time64'],1234567890123456799)
            self.assertEqual(row['relative_timestamp_s'],.0123)
            self.assertEqual(row['timing_status'],'TIMING_MISMATCH_UNRESOLVED')
            self.assertEqual(opened.bases['synthetic'].records.get(record.annotation_id).to_dict(),record.to_dict())
            self.assertEqual(opened.bases['synthetic'].frame_state(10),state)
            self.assertNotIn('.cine', ''.join(n for n in opened.files() if not n.endswith('.json')))
            self.assertEqual(opened.scheme,doc.scheme)

    def test_corruption_missing_and_unexpected_members(self):
        *_,pkg = fixture()
        files = pkg.files()
        name = next(n for n in files if n.endswith('.png'))
        files[name] += b'corrupt'
        with self.assertRaisesRegex(ValueError,'corruption'): ReviewPackage._from_files(files)
        files = pkg.files(); del files['manifest.json']
        with self.assertRaisesRegex(ValueError,'Missing'): ReviewPackage._from_files(files)
        files = pkg.files(); files['forbidden.cine'] = b'data'
        files['checksums/sha256.json'] = encode({k:digest(v) for k,v in files.items() if k!='checksums/sha256.json'})
        with self.assertRaisesRegex(ValueError,'Unexpected'): ReviewPackage._from_files(files)

    def test_traversal_absolute_and_duplicate_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            for name in ('../escape.txt','C:/file','/file','a/../../file','a\\file'):
                path = Path(tmp)/'bad.dvrpkg'
                with zipfile.ZipFile(path,'w') as archive: archive.writestr(name,b'bad')
                with self.assertRaises(ValueError): ReviewPackage.open(path)
            self.assertFalse((Path(tmp).parent/'escape.txt').exists())

    def test_absolute_metadata_rejected(self):
        *_,pkg = fixture()
        pkg.review['frame_notes']['synthetic:10'] = r'D:\private\source.cine'
        with self.assertRaisesRegex(ValueError,'absolute path'): pkg.files()

    def test_atomic_failure_preserves_destination(self):
        *_,pkg = fixture()
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)/'review.dvrpkg'
            pkg.save(path)
            before = path.read_bytes()
            pkg.start_review('reviewer')
            with patch('droplet_vision.review_package.bundle.os.replace',side_effect=OSError('simulated')):
                with self.assertRaises(OSError): pkg.save(path)
            self.assertEqual(path.read_bytes(),before)
            self.assertTrue(pkg.dirty)
            self.assertEqual(list(Path(tmp).iterdir()),[path])

    def test_snapshot_cannot_be_overwritten(self):
        *_,pkg = fixture()
        doc = pkg.documents['synthetic']
        # AnnotationStore returns copies; tamper with serialized payload to exercise the reader.
        files = pkg.files(); name = pkg.manifest['base_annotation_documents']['synthetic']['snapshot_path']
        value = json.loads(files[name]); value['document']['records'][0]['geometry']['points'][0] = [4,4]
        files[name] = encode(value)
        files['checksums/sha256.json'] = encode({k:digest(v) for k,v in files.items() if k!='checksums/sha256.json'})
        with self.assertRaisesRegex(ValueError,'overwritten'): ReviewPackage._from_files(files)

    def test_accept_reject_new_and_immutable_merge(self):
        doc,record,state,_,pkg = fixture()
        original = doc.to_dict()
        pkg.start_review('Reviewer alias')
        accepted = review_decision(pkg,'synthetic','object',record.annotation_id,'accepted')
        state_review = review_decision(pkg,'synthetic','state',state.record_id,'accepted')
        new = AnnotationRecord('synthetic',14,'daughter_droplet','point',{'point':[9,9]},attributes=pkg.provenance())
        pkg.documents['synthetic'].add_record(new)
        merged,conflicts = merge_review(doc,pkg)
        self.assertFalse(conflicts)
        self.assertEqual(doc.to_dict(),original)
        self.assertIn(record.annotation_id,merged.active_annotation_ids)
        self.assertEqual(merged.record_layers[accepted],'reviewed')
        self.assertEqual(merged.record_layers[new.annotation_id],'reviewed')
        self.assertEqual(merged.frame_state(10).record_id,state.record_id)
        self.assertIn(state_review,{r.record_id for r in merged.frame_state_records})
        self.assertEqual(merged.records.get(record.annotation_id).to_dict(),record.to_dict())
        again,_ = merge_review(merged,pkg)
        self.assertEqual(len(again.records.records()),len(merged.records.records()))
        rejected = review_decision(pkg,'synthetic','object',accepted,'rejected')
        merged,_ = merge_review(doc,pkg)
        self.assertIn(record.annotation_id,merged.active_annotation_ids)
        self.assertNotIn(rejected,merged.active_annotation_ids)
        self.assertEqual(merged.records.get(rejected).review_status,'rejected')

    def test_conflict_requires_choice_preserves_manual(self):
        doc,record,state,_,pkg = fixture()
        remote = review_decision(pkg,'synthetic','object',record.annotation_id,'accepted')
        local = doc.derive(record.annotation_id,{'points':[[4,4],[15,3],[15,15]]})
        doc.add_record(local); doc.transition(deactivate=[record.annotation_id])
        candidate,conflicts = merge_review(doc,pkg)
        self.assertEqual(len(conflicts),1)
        self.assertNotIn(remote,candidate.record_layers)
        key = conflicts[0]['conflict_id']
        for choice in ('local','defer','reviewer','both'):
            merged,_ = merge_review(doc,pkg,{key:choice})
            self.assertIn(local.annotation_id,merged.active_annotation_ids)
            self.assertEqual(remote in merged.record_layers,choice in ('reviewer','both'))
            self.assertEqual(merged.records.get(record.annotation_id).to_dict(),record.to_dict())

    def test_state_conflict_and_notes(self):
        doc,_,state,_,pkg = fixture()
        review_decision(pkg,'synthetic','state',state.record_id,'rejected')
        updated = FrameStateRecord('synthetic',10,state_ids=('burning',),derived_from=state.record_id)
        doc.add_frame_state(updated); doc.activate_frame_state(10,updated.record_id)
        pkg.review['frame_notes']['synthetic:10'] = 'Needs local verification'
        _,conflicts = merge_review(doc,pkg)
        self.assertEqual(conflicts[0]['kind'],'state')
        result,_ = merge_review(doc,pkg,{conflicts[0]['conflict_id']:'reviewer'})
        self.assertEqual(result.frame_state(10),updated)
        self.assertEqual(result.history[-1]['frame_notes'],pkg.review['frame_notes'])


if __name__ == '__main__':
    unittest.main()
