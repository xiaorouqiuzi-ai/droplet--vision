import sys
from pathlib import Path
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from droplet_vision.annotations.geometry import clamp_point, validate_geometry


class GeometryTests(unittest.TestCase):
    def test_valid_shapes_and_clamp(self):
        for kind, shape in [('point', {'point': [50, 50]}), ('bbox', {'bbox': [10, 20, 50, 60]}),
                            ('polygon', {'points': [[0, 0], [255, 0], [255, 255]]})]:
            validate_geometry(kind, shape, 256, 256)
        self.assertEqual(clamp_point([-4, 400], 256, 256), [0, 255])

    def test_invalid_bounds_nonfinite_degenerate(self):
        shapes = [('point', {'point': [float('nan'), 0]}), ('point', {'point': [256, 0]}),
                  ('point', {'point': [True, 0]}), ('bbox', {'bbox': [0, 0, 0, 1]}),
                  ('bbox', {'bbox': [250, 250, 10, 10]}), ('bbox', {'bbox': [0, 0, float('inf'), 2]}),
                  ('polygon', {'points': [[0, 0], [1, 1]]}),
                  ('polygon', {'points': [[0, 0], [2, 0], [2, -1]]}),
                  ('polygon', {'points': [[0, 0], [2, 0], [2, 2], [0, 0]]})]
        for kind, geometry in shapes:
            with self.subTest(kind=kind, geometry=geometry), self.assertRaises(ValueError):
                validate_geometry(kind, geometry, 256, 256)
