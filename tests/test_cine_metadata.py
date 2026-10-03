"""Serialization stays usable without importing NumPy/PIMS."""

import json
import sys
import unittest
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from droplet_vision.cine.metadata import CineMetadata


class MetadataTests(unittest.TestCase):
    def test_json_safe_whitelist(self):
        metadata = CineMetadata(path=Path('sample.cine'), serial=b'bad\xff\x00',
                                trigger_datetime=datetime(2026, 1, 1), fps_header=float('nan'))
        metadata.unlisted = object()
        result = metadata.to_dict()
        self.assertEqual(result['path'], 'sample.cine')
        self.assertEqual(result['trigger_datetime'], '2026-01-01T00:00:00')
        self.assertIsInstance(result['serial'], str)
        self.assertIsNone(result['fps_header'])
        self.assertNotIn('unlisted', result)
        self.assertIsNone(result['d_frame_rate'])
        self.assertIsNone(result['f_decimation'])
        json.dumps(result, allow_nan=False)

    def test_scalar_protocol_without_numpy_dependency(self):
        scalar = type('Scalar', (), {'__module__': 'numpy', 'ndim': 0, 'item': lambda self: 12})
        result = CineMetadata(frame_count=scalar()).to_dict()
        self.assertIs(type(result['frame_count']), int)
        json.dumps(result)
        floating = type('Floating', (float,), {'__module__': 'numpy', 'ndim': 0,
                                              'item': lambda self: float(self)})
        self.assertIs(type(CineMetadata(fps_header=floating(12)).to_dict()['fps_header']), float)

    def test_arbitrary_objects_rejected(self):
        with self.assertRaises(TypeError):
            CineMetadata(serial=object()).to_dict()


if __name__ == '__main__':
    unittest.main()
