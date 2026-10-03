import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from droplet_vision.annotations.taxonomy import load_taxonomy, default_taxonomy_path


class TaxonomyTests(unittest.TestCase):
    def test_unknown_label_requires_no_source_change(self):
        labels = load_taxonomy(Path(__file__).parent / "fixtures/experimental_taxonomy.json")
        self.assertEqual(labels[0].label_id, "experimental_feature_x")
        self.assertTrue(load_taxonomy(default_taxonomy_path()))
