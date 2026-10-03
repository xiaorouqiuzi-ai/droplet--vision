import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
import json
import tempfile
import unittest
from unittest.mock import patch
from droplet_vision.sampling import AnnotationQueue, AnnotationQueueItem
from droplet_vision.sampling.schema import stable_item_id, relative_path, resolve_relative


def item(index=5, cine='sample.cine'):
    return AnnotationQueueItem(cine, Path(cine).stem, Path(cine).name, index, 100, index/99,
                               2**60+index, index*.01, 'TIMING_UNKNOWN', ['anchor_0.03'], priority=50)


class QueueTests(unittest.TestCase):
    def test_stable_ids_status_notes_roundtrip_resume(self):
        first = item()
        self.assertEqual(first.item_id, item().item_id)
        self.assertNotEqual(first.item_id, item(cine='other/sample.cine').item_id)
        queue = AnnotationQueue('test', 'v1', 'DHVO', [first], {'version': 1})
        for status in ('IN_PROGRESS', 'DONE', 'SKIPPED', 'NEEDS_REVIEW', 'PENDING'):
            queue.update(first.item_id, status=status, notes='human note')
            self.assertEqual(first.status, status)
        with self.assertRaises(ValueError):
            queue.update(first.item_id, status='AUTOMATIC_EVENT')
        queue.update(first.item_id, status='DONE')
        queue.link_document('sample.cine', 'annotations/sample.json')
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)/'queue.json'
            queue.save(path)
            self.assertFalse(queue.dirty)
            loaded = AnnotationQueue.load(path)
            self.assertEqual(loaded.to_dict(), queue.to_dict())
            rebuilt = AnnotationQueue('test', 'v1', 'DHVO', [item()], {'version': 1})
            rebuilt.resume_from(loaded)
            self.assertEqual(rebuilt.items[0].status, 'DONE')
            self.assertEqual(rebuilt.items[0].notes, 'human note')
            self.assertEqual(rebuilt.items[0].annotation_document, 'annotations/sample.json')
            self.assertEqual(rebuilt.queue_id, loaded.queue_id)

    def test_atomic_failure_preserves_formal_json_and_dirty(self):
        queue = AnnotationQueue('test', 'v1', 'DHVO', [item()])
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)/'queue.json'
            queue.save(path)
            before = path.read_bytes()
            queue.update(queue.items[0].item_id, status='DONE')
            with patch('droplet_vision.sampling.queue.os.replace', side_effect=OSError('disk failure')):
                with self.assertRaises(OSError):
                    queue.save(path)
            self.assertEqual(path.read_bytes(), before)
            self.assertTrue(queue.dirty)
            self.assertEqual(list(Path(folder).glob('*.tmp')), [])

    def test_relative_paths_no_absolute_root_and_invalid_load(self):
        for path in ('C:/private/data.cine', '/tmp/file.cine', '../escape.cine', 'a/../x.cine', 'a\\x.cine'):
            with self.assertRaises(ValueError):
                relative_path(path)
        with self.assertRaises(ValueError):
            AnnotationQueue('name', 'v1', 'C:/private')
        queue = AnnotationQueue('test', 'v1', 'DHVO', [item()])
        payload = queue.to_dict()
        self.assertNotIn('dataset_root', payload)
        self.assertNotIn('pixels', json.dumps(payload))
        payload['items'][0]['item_id'] = 'wrong'
        with self.assertRaises(ValueError):
            AnnotationQueue.from_dict(payload)
        with self.assertRaises(ValueError):
            queue.link_document('sample.cine', '../annotations.json')

    def test_rebuild_cannot_lose_progress_or_accept_changed_source(self):
        queue = AnnotationQueue('test', 'v1', 'DHVO', [item()])
        empty = AnnotationQueue('test', 'v1', 'DHVO')
        with self.assertRaises(ValueError):
            empty.resume_from(queue)
        changed = AnnotationQueue('test', 'v1', 'DHVO', [item()])
        changed.items[0].cine_file_size = 99
        with self.assertRaises(ValueError):
            changed.resume_from(queue)
