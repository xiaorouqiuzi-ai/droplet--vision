import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from droplet_vision.annotations import AnnotationRecord, AnnotationLayer
from droplet_vision.annotations.schema import GEOMETRY_TYPES


class AnnotationSchemaTests(unittest.TestCase):
    def test_open_labels_geometry_and_roundtrip(self):
        for geometry_type in GEOMETRY_TYPES:
            record = AnnotationRecord("cine", 5, "previously_unseen_scientific_label", geometry_type,
                                      {"points": [[1.25, 2.5], [10, 4]]})
            layer = AnnotationLayer("future", "Future objects", annotations=[record])
            self.assertEqual(AnnotationLayer.from_dict(layer.to_dict()).to_dict(), layer.to_dict())

    def test_nonfinite_geometry_rejected(self):
        with self.assertRaises(ValueError):
            AnnotationRecord("cine", 0, "open_label", "point", {"point": [float('nan'), 2]})
