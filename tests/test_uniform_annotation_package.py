import os
from pathlib import Path
import tempfile
import sys
import unittest
from unittest.mock import patch
from types import SimpleNamespace
import numpy as np
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))

from droplet_vision.annotations import AnnotationDocument, AnnotationRecord
from droplet_vision.annotations.frame_state import FrameStateRecord
from droplet_vision.annotations.scheme import load_scheme
from droplet_vision.schema import FrameResult
from droplet_vision.sampling.uniform import uniform_frame_indices
from droplet_vision.review_package import AnnotationPackage, AnnotationFrameProvider, export_package, merge_review
from droplet_vision.review_package.cine_export import export_uniform_cine


def empty_package(count=100, samples=3):
    doc = AnnotationDocument('empty-cine', 'empty.cine', 123, count, 16, 16)
    doc.scheme = load_scheme()
    pixels = np.arange(256, dtype=np.uint8).reshape(16, 16)
    package = export_package([{'document': doc, 'targets': uniform_frame_indices(count, samples),
        'get_frame': lambda i: pixels, 'get_metadata': lambda i: FrameResult(doc.cine_id, i,
            timestamp_time64=1234567890123456789+i, timestamp_s=i*.005)}], doc.scheme, 0, purpose='annotation')
    return doc, pixels, package


class UniformIndicesTests(unittest.TestCase):
    def test_endpoints_exact_unique_and_rounding(self):
        self.assertEqual(uniform_frame_indices(100, 2), [0, 99])
        self.assertEqual(uniform_frame_indices(100, 3), [0, 50, 99])
        for count, samples in [(32196, 50), (50, 50), (10, 50), (1, 50), (2**60, 50)]:
            values = uniform_frame_indices(count, samples)
            self.assertEqual(len(values), min(count, samples))
            self.assertEqual(values, sorted(set(values)))
            self.assertEqual((values[0], values[-1]), (0, count-1))
            self.assertEqual(values, uniform_frame_indices(count, samples))
        self.assertEqual(uniform_frame_indices(50, 50), list(range(50)))
        self.assertEqual(uniform_frame_indices(10, 50), list(range(10)))

    def test_validation_and_exhaustive_small_intervals(self):
        for bad in [(0, 5), (-1, 5), (10, 1), (True, 5), (10, 2.5)]:
            with self.assertRaises(ValueError): uniform_frame_indices(*bad)
        for count in range(2, 100):
            for samples in range(2, count+1):
                indices = uniform_frame_indices(count, samples)
                self.assertEqual(indices, [round(i*(count-1)/(samples-1)) for i in range(samples)])
                intervals = np.diff(indices)
                self.assertLessEqual(max(intervals)-min(intervals), 1)


class AnnotationV2Tests(unittest.TestCase):
    def test_empty_add_save_reload_merge_and_progress(self):
        original, pixels, package = empty_package()
        self.assertEqual(package.summary()['annotations'], 0)
        self.assertEqual(package.summary()['frame_states'], 0)
        self.assertEqual(package.progress(original.cine_id), (3, 0, 3))
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)/'raw.dvapkg'
            package.save(path)
            opened = AnnotationPackage.open(path)
            self.assertEqual(opened.manifest['package_format_version'], 2)
            self.assertEqual(opened.manifest['package_purpose'], 'annotation')
            provider = AnnotationFrameProvider(opened)
            for i in (0, 50, 99):
                np.testing.assert_array_equal(provider.get_frame(original.cine_id, i), pixels)
            doc = opened.documents[original.cine_id]
            record = AnnotationRecord(doc.cine_id, 50, 'parent_droplet', 'polygon',
                                      {'points': [[1,1], [12,1], [12,12]]}, attributes=opened.provenance())
            doc.add_record(record)
            state = FrameStateRecord(doc.cine_id, 50, state_ids=('burning',))
            doc.add_frame_state(state); doc.activate_frame_state(50, state.record_id)
            opened.review['record_provenance'][state.record_id] = opened.provenance()
            self.assertEqual(opened.progress(doc.cine_id), (3, 1, 2))
            opened.review['reviewed_frames'].append([doc.cine_id, 99])
            self.assertEqual(opened.progress(doc.cine_id), (3, 2, 1))
            returned = Path(tmp)/'annotated.dvapkg'; opened.save(returned)
            loaded = AnnotationPackage.open(returned)
            # A newly opened Cine has a different empty AnnotationDocument UUID.
            local = AnnotationDocument(doc.cine_id, doc.cine_filename, doc.cine_file_size,
                                       doc.frame_count, doc.width, doc.height)
            merged, conflicts = merge_review(local, loaded)
            self.assertFalse(conflicts)
            self.assertEqual(merged.record_layers[record.annotation_id], 'reviewed')
            self.assertIn(record.annotation_id, merged.active_annotation_ids)
            self.assertIn(state.record_id, {r.record_id for r in merged.frame_state_records})
            self.assertIsNone(merged.frame_state(50))  # State stays a candidate, not auto-approved.
            again, conflicts = merge_review(merged, loaded)
            self.assertEqual(len(again.records.records()), 1)
            self.assertFalse(conflicts)

    def test_legacy_v1_missing_kind_and_metadata_retained(self):
        from test_review_package import fixture
        _, _, _, _, package = fixture()
        package.manifest['package_format_version'] = 1
        package.manifest.pop('package_kind'); package.manifest.pop('package_purpose')
        package.review['reviewer'] = {'display_name': 'legacy reviewer'}
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)/'legacy.dvrpkg'
            package.save(path)
            opened = AnnotationPackage.open(path)
            self.assertEqual(opened.review['reviewer'], {'display_name': 'legacy reviewer'})
            self.assertEqual(opened.summary()['annotations'], 1)

    def test_nonempty_base_keeps_strict_identity_and_cine_checks(self):
        from test_review_package import fixture
        doc, _, _, _, package = fixture()
        doc.document_id = 'another-document'
        with self.assertRaises(ValueError): merge_review(doc, package)
        doc, _, package = empty_package()
        doc.cine_file_size += 1
        with self.assertRaises(ValueError): merge_review(doc, package)

    def test_invalid_v2_and_forged_standalone_base(self):
        from test_review_package import fixture
        doc, _, _, _, package = fixture()
        package.manifest['base_annotation_documents'][doc.cine_id]['standalone_empty_base'] = True
        with self.assertRaisesRegex(ValueError, 'Standalone'): AnnotationPackage._from_files(package.files())
        _, _, package = empty_package()
        package.manifest['package_kind'] = 'other'
        with self.assertRaisesRegex(ValueError, 'kind'): AnnotationPackage._from_files(package.files())

    def test_short_cine_confirmation_source_safety_context_and_sampling(self):
        info = {'cine_id': 'small', 'filename': 'test.cine', 'file_size_bytes': 1,
                'mtime_ns': 1, 'frame_count': 3, 'width': 16, 'height': 16}
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); (root/'source').mkdir(); (root/'out').mkdir()
            source = root/'source/test.cine'; source.write_bytes(b'x')
            dest = root/'out/test.dvapkg'
            with patch('droplet_vision.review_package.cine_export.inspect_cine', return_value=info):
                with self.assertRaisesRegex(ValueError, 'Confirm'):
                    export_uniform_cine(source, dest, 50, load_scheme())
                with self.assertRaisesRegex(ValueError, 'source Cine directory'):
                    export_uniform_cine(source, source.with_suffix('.dvapkg'), 50, load_scheme())
                with self.assertRaisesRegex(ValueError, 'changed since'):
                    export_uniform_cine(source, dest, 50, load_scheme(), expected={})
            self.assertFalse(dest.exists())

    def test_lazy_adapter_short_fallback_context_and_source_change(self):
        decoded = []
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); (root/'source').mkdir(); (root/'out').mkdir()
            source = root/'source/test.cine'; source.write_bytes(b'x')
            destination = root/'out/uniform.dvapkg'

            class Reader:
                def __init__(self, path):
                    self.metadata = SimpleNamespace(filename='test.cine', file_size_bytes=1,
                                                    frame_count=10, width=16, height=16)
                def __enter__(self): return self
                def __exit__(self, *args): pass
                def build_frame_result(self, i): return FrameResult('test', i, timestamp_time64=2**60+i)
                def read_frame(self, i):
                    decoded.append(i)
                    return np.full((16,16), i+10, np.uint8)

            with patch('droplet_vision.review_package.cine_export.CineReader', Reader):
                package = export_uniform_cine(source, destination, 2, load_scheme(), context=1)
                self.assertEqual(package.summary()['target_frames'], 2)
                self.assertEqual(package.summary()['context_frames'], 2)
                self.assertEqual(sorted(decoded), [0,0,1,8,9])  # Reference + selected/context only.
                package.manifest['sampling']['actual_target_count'] = 3
                with self.assertRaisesRegex(ValueError, 'inventory'):
                    AnnotationPackage._from_files(package.files())
                decoded.clear()
                all_frames = export_uniform_cine(source, destination, 50, load_scheme(), allow_short=True)
                self.assertEqual(all_frames.summary()['target_frames'], 10)
                self.assertEqual(all_frames.manifest['sampling']['frame_indices'], list(range(10)))
                old_package = destination.read_bytes()
                def changed(reader, i):
                    source.write_bytes(b'changed synthetic test data')
                    return np.full((16,16), 10, np.uint8)
                with patch.object(Reader, 'read_frame', changed):
                    with self.assertRaisesRegex(RuntimeError, 'SOURCE CHANGED'):
                        export_uniform_cine(source, destination, 2, load_scheme())
                self.assertEqual(destination.read_bytes(), old_package)


@unittest.skipUnless(os.environ.get('DROPLET_VISION_LAYOUT_TEST_CINE'), 'Set D60 integration Cine')
class RealUniformPackageTests(unittest.TestCase):
    def test_fifty_raw_frames_zero_base_return_and_source_unchanged(self):
        from droplet_vision.cine import CineReader
        source = Path(os.environ['DROPLET_VISION_LAYOUT_TEST_CINE'])
        before = source.stat()
        members = set(source.parent.iterdir())
        with tempfile.TemporaryDirectory() as tmp:
            package = export_uniform_cine(source, Path(tmp)/'uniform50.dvapkg', 50, load_scheme())
            self.assertEqual(package.summary()['target_frames'], 50)
            self.assertEqual(package.summary()['context_frames'], 0)
            self.assertEqual(package.summary()['annotations'], 0)
            cid = next(iter(package.documents)); provider = AnnotationFrameProvider(package)
            with CineReader(source) as reader:
                indices = provider.available(cid)
                self.assertEqual(indices, uniform_frame_indices(reader.metadata.frame_count, 50))
                for i in indices:
                    np.testing.assert_array_equal(provider.get_frame(cid, i), reader.read_frame(i))
                    self.assertEqual(provider.metadata[cid, i]['raw_time64'], reader.build_frame_result(i).timestamp_time64)
                    self.assertEqual(provider.metadata[cid, i]['relative_timestamp_s'], reader.build_frame_result(i).timestamp_s)
                    self.assertEqual(provider.metadata[cid, i]['timing_status'], reader.build_frame_result(i).timing_status.value)
            self.assertIsNotNone(package.manifest['photometric'][cid])
        after = source.stat()
        self.assertEqual((before.st_size, before.st_mtime_ns), (after.st_size, after.st_mtime_ns))
        self.assertEqual(members, set(source.parent.iterdir()))
