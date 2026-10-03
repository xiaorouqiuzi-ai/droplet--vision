import json
import sys
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from droplet_vision.annotations import AnnotationDocument, AnnotationRecord


def document():
    return AnnotationDocument('sample', 'sample.cine', 100, 1000, 256, 256,
                              {'reference': 'arbitrary_taxonomy.json'})


class DocumentTests(unittest.TestCase):
    def test_arbitrary_labels_edit_history_deactivate_roundtrip(self):
        doc = document()
        self.assertFalse(doc.dirty)
        record = AnnotationRecord('sample', 4, 'experimental_feature_x', 'point', {'point': [50, 50]},
                                  attributes={'raw_time64': 123456, 'relative_timestamp_s': .1})
        doc.add_record(record)
        original = doc.records.get(record.annotation_id).to_dict()
        changed = doc.derive(record.annotation_id, {'point': [60, 50]})
        doc.add_record(changed, activate=False)
        doc.transition(activate=[changed.annotation_id], deactivate=[record.annotation_id], reason='edit')
        self.assertEqual(doc.records.get(record.annotation_id).to_dict(), original)
        self.assertEqual(doc.annotated_frames(), [4])
        self.assertEqual(changed.attributes['raw_time64'], 123456)
        self.assertTrue(doc.dirty)
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'annotations.json'
            doc.save(path)
            self.assertFalse(doc.dirty)
            loaded = AnnotationDocument.load(path)
            self.assertEqual(loaded.to_dict(), doc.to_dict())
            self.assertEqual(len(loaded.records.records()), 2)
            loaded.transition(deactivate=[changed.annotation_id], reason='user_delete')
            self.assertTrue(loaded.dirty)
            self.assertEqual(loaded.active_records(), [])
            self.assertEqual(len(loaded.records.records()), 2)

    def test_prediction_derivative_preserves_original_and_ground_truth_backend(self):
        doc = document()
        prediction = AnnotationRecord('sample', 2, 'new_label', 'polygon',
                                      {'points': [[10, 10], [50, 10], [50, 50]]},
                                      source='model', model_id='test_model', confidence=.81)
        doc.add_record(prediction, 'prediction')
        before = prediction.to_dict()
        reviewed = doc.derive(prediction.annotation_id, {'points': [[11, 10], [50, 10], [50, 50]]})
        doc.add_record(reviewed, 'reviewed')
        self.assertEqual(reviewed.source, 'manual')
        self.assertEqual(reviewed.review_status, 'edited')
        self.assertEqual(reviewed.derived_from, prediction.annotation_id)
        self.assertIsNone(reviewed.model_id)
        self.assertIsNone(reviewed.confidence)
        ground_truth = doc.derive(reviewed.annotation_id, review_status='ground_truth')
        doc.add_record(ground_truth, 'ground_truth')
        self.assertEqual(doc.records.get(prediction.annotation_id).to_dict(), before)

    def test_atomic_failure_keeps_formal_file_and_dirty_autosave(self):
        doc = document()
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'annotations.json'
            doc.save(path)
            before = path.read_bytes()
            doc.add_record(AnnotationRecord('sample', 0, 'label', 'point', {'point': [1, 2]}))
            for method in ('os.replace', 'os.fsync'):
                with patch('droplet_vision.annotations.document.' + method, side_effect=OSError('simulated failure')):
                    with self.assertRaises(OSError):
                        doc.save(path)
                self.assertEqual(path.read_bytes(), before)
                AnnotationDocument.load(path)
                self.assertTrue(doc.dirty)
                self.assertEqual(list(Path(folder).glob('*.tmp')), [])
            doc.save(Path(folder) / 'autosave.json', mark_saved=False)
            self.assertTrue(doc.dirty)
            with patch('droplet_vision.annotations.document.os.fsync', wraps=__import__('os').fsync) as fsync:
                doc.save(path)
                self.assertTrue(fsync.called)
            self.assertFalse(doc.dirty)

    def test_invalid_document_load_and_portable_identity(self):
        doc = document()
        record = AnnotationRecord('sample', 0, 'label', 'point', {'point': [1, 2]})
        doc.add_record(record)
        for change in ('bounds', 'ids', 'history'):
            value = doc.to_dict()
            if change == 'bounds':
                value['records'][0]['geometry']['point'] = [-1, 2]
            elif change == 'ids':
                value['active_annotation_ids'].append('missing')
            else:
                value['records'][0]['derived_from'] = record.annotation_id
            with self.assertRaises(ValueError):
                AnnotationDocument.from_dict(value)
        with self.assertRaises(ValueError):
            AnnotationDocument('sample', '../sample.cine', 100, 1, 256, 256)
        self.assertNotIn('pixels', doc.to_dict())
        with self.assertRaises(ValueError):
            doc.save('invalid.cine')
