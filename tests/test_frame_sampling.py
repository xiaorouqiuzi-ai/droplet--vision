import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from dataclasses import replace
from types import SimpleNamespace
import tempfile
import unittest
import numpy as np
from droplet_vision.enums import TimingStatus
from droplet_vision.schema import FrameResult
from droplet_vision.sampling import load_sampling_config, sample_reader, build_annotation_queue, SourceChangedError
from droplet_vision.sampling.sampler import anchor_indices, probe_indices, change_score, select_intervals, outside_source


class StepReader:
    def __init__(self, count=101):
        self.metadata = SimpleNamespace(frame_count=count)
        self.reads = []

    def read_frame(self, index):
        self.reads.append(index)
        return np.full((8, 8), 20 if index < self.metadata.frame_count//2 else 200, dtype=np.uint8)

    def build_frame_result(self, index):
        return FrameResult('sample', index, timestamp_time64=2**60+index*100,
                           timestamp_s=index*100/2**32, timing_status=TimingStatus.TIMING_MISMATCH_UNRESOLVED)

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass


class SamplingTests(unittest.TestCase):
    def setUp(self):
        self.config = load_sampling_config()

    def test_config_anchor_rounding_short_dedupe(self):
        anchors = anchor_indices(32196, self.config.anchor_fractions)
        self.assertEqual(anchors[966], ['anchor_0.03'])
        items, report = sample_reader(StepReader(1), 'sample.cine', self.config)
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].frame_fraction, 0)
        self.assertEqual(len(items[0].sample_reasons), 11)
        self.assertEqual(report['total_decoded'], 1)
        with self.assertRaises(ValueError):
            replace(self.config, max_probe_frames=513)

    def test_probe_bound_order_and_streaming_decode_accounting(self):
        reader = StepReader(32196)
        items, report = sample_reader(reader, 'sample.cine', self.config)
        self.assertEqual(reader.reads[:512], probe_indices(32196, 512))
        self.assertEqual(len(set(reader.reads[:512])), 512)
        self.assertEqual(report['total_decoded'], len(reader.reads))
        self.assertLess(report['total_decoded'], 32196//10)
        self.assertLessEqual(len(items), 19)
        self.assertEqual(probe_indices(3, 512), [0, 1, 2])

    def test_raw_float_score_immutability_and_supported_dtype(self):
        first = np.full((8, 8), 250, dtype=np.uint8)
        second = np.full((8, 8), 5, dtype=np.uint8)
        self.assertAlmostEqual(change_score(first, second), 245/255, places=6)
        self.assertTrue(np.all(first == 250))
        with self.assertRaises(ValueError):
            change_score(first.astype(np.uint16), second)

    def test_refinement_merge_provenance_no_physical_labels(self):
        config = replace(self.config, max_probe_frames=3)
        items, report = sample_reader(StepReader(), 'sample.cine', config)
        peak = next(i for i in items if 'change_peak' in i.sample_reasons)
        self.assertEqual(peak.frame_index, 50)
        self.assertEqual(peak.sample_reasons, ['anchor_0.50', 'change_peak'])
        self.assertEqual((peak.coarse_left, peak.coarse_right, peak.local_peak_previous_frame), (0, 50, 49))
        self.assertEqual(peak.priority, config.change_peak_priority)
        self.assertEqual(peak.raw_time64, 2**60+5000)
        self.assertAlmostEqual(peak.relative_timestamp_s, 5000/2**32)
        self.assertTrue(all(r.startswith('anchor_') or r == 'change_peak' for i in items for r in i.sample_reasons))

    def test_diversity_ties_and_flat_cine(self):
        intervals = [{'left': l, 'right': l+10, 'score': s} for l, s in [(0, .5), (10, .5), (40, .4), (80, 0)]]
        self.assertEqual([i['left'] for i in select_intervals(intervals, 8, 25)], [0, 40])
        reader = StepReader()
        reader.read_frame = lambda index: np.zeros((8, 8), dtype=np.uint8)
        items, report = sample_reader(reader, 'sample.cine')
        self.assertEqual(report['refinement_frames'], 0)
        self.assertTrue(all(i.change_score is None for i in items))

    def test_failure_isolation_and_source_change_stops(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root/'good.cine').write_bytes(b'unit test placeholder; never parsed')
            (root/'bad.CINE').write_bytes(b'unit test placeholder')
            (root/'note.txt').write_text('ignored')
            def factory(path):
                if path.name == 'bad.CINE':
                    raise ValueError('bad input')
                return StepReader(3)
            queue = build_annotation_queue(root, reader_factory=factory)
            self.assertEqual(len(queue.failed_files), 1)
            self.assertEqual(len(queue.sampling_report), 1)
            def changed(path):
                path.write_bytes(b'changed synthetic input')
                return StepReader(3)
            with self.assertRaises(SourceChangedError):
                build_annotation_queue(root, reader_factory=changed)
            with self.assertRaises(ValueError):
                outside_source(root/'queue.json', root)
