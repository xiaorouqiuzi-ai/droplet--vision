import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from droplet_vision.annotations.document import AnnotationDocument
from droplet_vision.annotations.frame_state import FrameStateRecord
from droplet_vision.annotations.scheme import load_scheme, save_custom_scheme, suggest_instance_name, validate_scheme
from droplet_vision.annotations.schema import AnnotationRecord


class FrameStateTests(unittest.TestCase):
    def document(self):
        return AnnotationDocument('cine', 'sample.cine', 99, 100, 256, 256)

    def test_scheme_registry_and_exclusions(self):
        scheme = load_scheme()
        self.assertEqual(len(scheme['objects']['labels']), 6)
        states = [r['state_id'] for r in scheme['frame_states']['states']]
        self.assertEqual(len(states), 10)
        self.assertEqual([r['flag_id'] for r in scheme['frame_states']['quality_flags']], ['uncertain'])
        self.assertFalse(set(states) & {'ignition', 'auto_ignition', 'bursting', 'uncertain'})
        self.assertEqual(sum(r['group'] == 'dynamic' for r in scheme['frame_states']['states']), 2)

    def test_custom_copy_cannot_overwrite_and_keeps_ids(self):
        scheme = load_scheme()
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)/'custom.json'
            with self.assertRaises(ValueError):
                save_custom_scheme(scheme, path)
            scheme.update(scheme_id='custom_01', status='custom')
            scheme['objects']['labels'][0]['display_name'] = 'My parent'
            save_custom_scheme(scheme, path)
            loaded = load_scheme(path)
            self.assertEqual(loaded['objects']['labels'][0]['label_id'], 'parent_droplet')
            with self.assertRaises(FileExistsError):
                save_custom_scheme(scheme, path)

    def test_tampered_approved_scheme_and_document_rejected(self):
        scheme = load_scheme()
        scheme['objects']['labels'][0]['label_id'] = 'renamed'
        with self.assertRaises(ValueError):
            validate_scheme(scheme)
        value = self.document().to_dict()
        value['scheme'] = scheme
        with self.assertRaises(ValueError):
            AnnotationDocument.from_dict(value)

    def test_separate_quality_finite_time_and_exclusivity(self):
        record = FrameStateRecord('cine', 3, 7130238840138969063, .125,
                                  ('nucleation', 'bubble_growth'), True, 'review later')
        value = record.to_dict()
        self.assertEqual(value['quality'], {'uncertain': True})
        self.assertNotIn('uncertain', value['state_ids'])
        self.assertEqual(FrameStateRecord.from_dict(value), record)
        for states in [('uncertain',), ('ignition',), ('simple_evaporation', 'burning')]:
            with self.assertRaises(ValueError):
                FrameStateRecord('cine', 3, state_ids=states)
        with self.assertRaises(ValueError):
            FrameStateRecord('cine', 3, relative_timestamp_s=float('nan'))

    def test_history_active_pointer_roundtrip_and_dirty(self):
        doc = self.document()
        first = FrameStateRecord('cine', 3, state_ids=('nucleation',))
        second = FrameStateRecord('cine', 3, state_ids=('nucleation', 'bubble_growth'), derived_from=first.record_id)
        doc.add_frame_state(first)
        doc.add_frame_state(second)
        doc.activate_frame_state(3, second.record_id)
        self.assertTrue(doc.dirty)
        self.assertEqual(len(doc.records.records()), 0)
        pointer = doc.active_frame_state_records
        pointer.clear()
        self.assertEqual(doc.frame_state(3), second)
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)/'a.json'
            doc.save(path)
            self.assertFalse(doc.dirty)
            loaded = AnnotationDocument.load(path)
            self.assertEqual(loaded.to_dict(), doc.to_dict())
            self.assertEqual(loaded.frame_state(3), second)
            self.assertEqual(loaded.frame_state_records[0], first)
            with patch('droplet_vision.annotations.document.os.replace', side_effect=OSError('fail')):
                with self.assertRaises(OSError):
                    doc.save(path)
            self.assertEqual(AnnotationDocument.load(path).to_dict(), loaded.to_dict())

    def test_legacy_document_and_invalid_pointer(self):
        value = self.document().to_dict()
        value.pop('frame_state_records')
        value.pop('active_frame_state_records')
        value.pop('scheme')
        loaded = AnnotationDocument.from_dict(value)
        self.assertEqual(loaded.frame_state_records, ())
        self.assertIsNone(loaded.frame_state(0))
        value['active_frame_state_records'] = {'1': 'missing'}
        with self.assertRaises(ValueError):
            AnnotationDocument.from_dict(value)

    def test_invalid_history_preserves_existing(self):
        doc = self.document()
        original = FrameStateRecord('cine', 1)
        doc.add_frame_state(original)
        with self.assertRaises(ValueError):
            doc.add_frame_state(FrameStateRecord('cine', 2, derived_from=original.record_id))
        with self.assertRaises(ValueError):
            doc.add_frame_state(original)
        self.assertEqual(doc.frame_state_records, (original,))

    def test_optional_name_and_frame_local_suggestion(self):
        doc = self.document()
        prefixes = load_scheme()['instance_prefixes']
        record = AnnotationRecord('cine', 3, 'parent_droplet', 'point', {'point': [5, 5]},
                                  attributes={'instance_name': 'Parent_01'})
        doc.add_record(record)
        self.assertEqual(suggest_instance_name(doc, 3, 'parent_droplet', prefixes), 'Parent_02')
        self.assertEqual(suggest_instance_name(doc, 4, 'parent_droplet', prefixes), 'Parent_01')
