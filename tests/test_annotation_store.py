import sys
import tempfile
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from droplet_vision.annotations import AnnotationRecord, AnnotationStore


class StoreTests(unittest.TestCase):
    def test_review_preserves_prediction_and_roundtrip(self):
        prediction = AnnotationRecord("cine", 0, "any_object", "point", {"point": [1, 2]},
                                      source="model", model_id="test_model", confidence=.8)
        original = prediction.to_dict()
        store = AnnotationStore()
        store.add(prediction)
        prediction.geometry["point"][0] = 200
        reviewed = store.review(prediction.annotation_id, "edited", "reviewer", {"point": [2, 3]})
        self.assertEqual(store.get(prediction.annotation_id).to_dict(), original)
        self.assertEqual(reviewed.derived_from, prediction.annotation_id)
        self.assertNotEqual(reviewed.annotation_id, prediction.annotation_id)
        with self.assertRaises(ValueError):
            store.add(prediction)
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "annotations.json"
            store.save(path)
            self.assertEqual([r.to_dict() for r in AnnotationStore.load(path).records()],
                             [r.to_dict() for r in store.records()])
