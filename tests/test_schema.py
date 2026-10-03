"""Run from a source checkout without installing the package."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from droplet_vision import DropletState, FrameMetrics, FrameResult, ObjectType, TimingStatus


class SchemaTests(unittest.TestCase):
    def test_droplet_state(self):
        self.assertEqual(DropletState("NUCLEATION"), DropletState.NUCLEATION)
        self.assertEqual(len(DropletState), 8)

    def test_frame_result(self):
        frame = FrameResult("example", 0, state=DropletState.UNCERTAIN)
        self.assertIsNone(frame.parent_mask)
        self.assertIsNone(frame.timestamp_s)
        self.assertEqual(frame.state, DropletState.UNCERTAIN)

    def test_metadata_is_not_shared(self):
        first, second = FrameResult("example", 0), FrameResult("example", 1)
        first.metadata["source"] = "test"
        self.assertEqual(second.metadata, {})

    def test_partial_metrics(self):
        metrics = FrameMetrics(parent_area_px=12.0, daughter_count=0)
        self.assertEqual(metrics.parent_area_px, 12.0)
        self.assertEqual(metrics.daughter_count, 0)
        self.assertIsNone(metrics.cavity_count)
        self.assertIsNone(metrics.parent_deq_px)

    def test_timing_status(self):
        status = TimingStatus("TIMING_MISMATCH_UNRESOLVED")
        frame = FrameResult("example", 0, timestamp_time64=2**60 + 1, timing_status=status)
        self.assertEqual(frame.timestamp_time64, 2**60 + 1)
        self.assertEqual(frame.timing_status, status)
        self.assertEqual(FrameResult("example", 1).timing_status, TimingStatus.TIMING_UNKNOWN)

    def test_spatial_label(self):
        self.assertEqual(ObjectType.INTERNAL_CAVITY_CANDIDATE.value, "internal_cavity_candidate")


if __name__ == "__main__":
    unittest.main()
