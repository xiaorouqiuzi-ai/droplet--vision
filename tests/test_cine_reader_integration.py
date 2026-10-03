"""Opt-in real-file tests; 2 us tolerance is parser agreement, not uncertainty."""

import os
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from droplet_vision.cine import CineReader
from droplet_vision.cine.timing import relative_times_seconds


@unittest.skipUnless(os.environ.get('DROPLET_VISION_TEST_CINE'), 'DROPLET_VISION_TEST_CINE is not set')
class CineIntegrationTests(unittest.TestCase):
    def test_frames_timestamps_and_reopen(self):
        import numpy as np
        from pims import Cine

        path = Path(os.environ['DROPLET_VISION_TEST_CINE'])
        before = path.stat()
        with CineReader(path) as reader:
            self.assertGreater(len(reader), 1)
            indices = [len(reader) - 1, 0, len(reader) // 2, 0]
            with Cine(str(path)) as pims_reader:
                for index, frame in zip(indices, reader.read_frames(iter(indices))):
                    self.assertEqual(frame.shape, reader.frame_shape)
                    self.assertEqual(frame.dtype, reader.pixel_dtype)
                    np.testing.assert_array_equal(frame, pims_reader[index])
                original = reader.read_frame(0)
                changed = reader.read_frame(0)
                changed.flat[0] = 0 if original.flat[0] else 1
                np.testing.assert_array_equal(reader.read_frame(0), original)
                self.assertEqual(len(reader.raw_time64), len(reader))
                self.assertEqual(reader.timing_summary.timestamp_count, len(reader))
                self.assertTrue(reader.timing_summary.timestamps_monotonic)
                raw_relative = relative_times_seconds(reader.raw_time64)
                zero = pims_reader.get_time_to_trigger(0)
                max_difference = max(abs(raw_relative[i] - (pims_reader.get_time_to_trigger(i) - zero))
                                     for i in range(len(reader)))
                self.assertLessEqual(max_difference, 2e-6,
                                     '2 us is parser cross-check tolerance, not measurement uncertainty')
            result = reader.build_frame_result(indices[0])
            self.assertEqual(result.timestamp_time64, reader.raw_time64[indices[0]])
            self.assertEqual(result.timestamp_s, raw_relative[indices[0]])
            self.assertIsNone(result.parent_mask)
            self.assertIsNone(result.state)
            for index in (-1, len(reader)):
                with self.assertRaises(IndexError):
                    reader.read_frame(index)
            with self.assertRaises(TypeError):
                reader.read_frame(0.5)
        self.assertTrue(reader.closed)
        reader.close()
        with self.assertRaises(ValueError):
            reader.read_frame(0)
        with CineReader(path) as reopened:
            self.assertEqual(len(reopened), len(reader))
            reopened.read_frame(0)
        after = path.stat()
        self.assertEqual((before.st_size, before.st_mtime_ns), (after.st_size, after.st_mtime_ns))


if __name__ == '__main__':
    unittest.main()
