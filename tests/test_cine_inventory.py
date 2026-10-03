"""Temporary discovery/output files and mocked inspection; no real Cine."""

import csv
import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from droplet_vision.cine.inventory import (
    build_inventory, discover_cine_files, inspect_cine, write_inventory_csv, write_inventory_json,
)
from droplet_vision.cine.metadata import CineMetadata
from droplet_vision.cine.timing import summarize_timing


class InventoryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / 'nested').mkdir()
        (self.root / 'a.CINE').write_bytes(b'not a cine')
        (self.root / 'nested/b.cine').write_bytes(b'not a cine')
        (self.root / 'ignore.txt').write_text('not a cine')

    def test_discovery(self):
        self.assertEqual(len(discover_cine_files(self.root)), 2)
        self.assertEqual(len(discover_cine_files(self.root, recursive=False)), 1)

    def test_error_isolation_strict_and_portable_outputs(self):
        with patch('droplet_vision.cine.inventory.CineReader', side_effect=ValueError('bad header')):
            rows = build_inventory(self.root)
            self.assertEqual(len(rows), 2)
            self.assertTrue(all(not row['readable'] for row in rows))
            with self.assertRaises(ValueError):
                build_inventory(self.root, strict=True)
        self.assertEqual([row['relative_path'] for row in rows], ['a.CINE', 'nested/b.cine'])
        write_inventory_csv(rows, self.root / 'inventory.csv')
        write_inventory_json(rows, self.root / 'inventory.json', scan_root=self.root)
        content = (self.root / 'inventory.json').read_text(encoding='utf-8')
        self.assertNotIn(str(self.root), content)
        self.assertNotIn('scan_root', json.loads(content))
        with (self.root / 'inventory.csv').open(newline='', encoding='utf-8') as stream:
            self.assertEqual(len(list(csv.DictReader(stream))), 2)
        write_inventory_json([], self.root / 'empty.json', self.root, include_absolute_root=True)
        self.assertEqual(json.loads((self.root / 'empty.json').read_text())['scan_root'], str(self.root))

    def test_success_hash_opt_in_and_no_pixels(self):
        reader = MagicMock()
        reader.metadata = CineMetadata(filename='a.CINE', frame_count=2)
        reader.timing_summary = summarize_timing([0, 2**32], 2)
        reader.__enter__.return_value = reader
        with patch('droplet_vision.cine.inventory.CineReader', return_value=reader):
            with patch('droplet_vision.cine.inventory._sha256') as digest:
                row = inspect_cine(self.root / 'a.CINE')
                digest.assert_not_called()
            self.assertTrue(row['readable'])
            self.assertIsNone(row['sha256'])
            row = inspect_cine(self.root / 'a.CINE', compute_hash=True)
            self.assertEqual(row['sha256'], hashlib.sha256(b'not a cine').hexdigest())
            self.assertEqual(row['interval_mean_us'], 1e6)
            reader.read_frame.assert_not_called()

    def test_absolute_error_path_removed(self):
        path = self.root / 'a.CINE'
        for error in (ValueError(str(path)), PermissionError(13, 'Permission denied', str(path))):
            with patch('droplet_vision.cine.inventory.CineReader', side_effect=error):
                row = inspect_cine(path)
            self.assertNotIn(str(self.root), row['error_message'])
            self.assertNotIn(repr(str(self.root))[1:-1], row['error_message'])
            self.assertIn('a.CINE', row['error_message'])

    def test_output_cannot_overwrite_cine(self):
        for writer in (write_inventory_csv, write_inventory_json):
            with self.assertRaises(ValueError):
                writer([], self.root / 'a.CINE')
        self.assertEqual((self.root / 'a.CINE').read_bytes(), b'not a cine')


if __name__ == '__main__':
    unittest.main()
