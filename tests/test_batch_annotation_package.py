import json
import os
from pathlib import Path
import sys
import tempfile
from threading import Event
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import zipfile

import numpy as np
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from droplet_vision.annotations.scheme import load_scheme
from droplet_vision.schema import FrameResult
from droplet_vision.review_package import AnnotationPackage, AnnotationFrameProvider
from droplet_vision.review_package.batch import (discover_cines, map_cine_to_package_path,
    scan_batch, execute_batch, BatchCancelled)
from droplet_vision.review_package.cine_export import export_uniform_cine
from droplet_vision.sampling.uniform import uniform_frame_indices


class SyntheticReader:
    reads = []
    open_count = peak_open = 0

    def __init__(self, path):
        self.path = Path(path)
        count = int(self.path.read_text())
        self.metadata = SimpleNamespace(filename=self.path.name, file_size_bytes=self.path.stat().st_size,
                                        frame_count=count, width=16, height=16)

    def __enter__(self):
        type(self).open_count += 1
        type(self).peak_open = max(type(self).peak_open, type(self).open_count)
        return self

    def __exit__(self, *args):
        type(self).open_count -= 1

    def build_frame_result(self, index):
        return FrameResult(self.path.stem, index, timestamp_time64=2**60+index, timestamp_s=index*.001)

    def read_frame(self, index):
        type(self).reads.append((self.path.name, index))
        return np.full((16, 16), 10+index % 200, np.uint8)


class BatchPackageTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.source, self.output = self.root/'A', self.root/'Packages'
        self.source.mkdir()
        self.scheme = load_scheme()
        SyntheticReader.reads = []
        SyntheticReader.open_count = SyntheticReader.peak_open = 0
        p = patch('droplet_vision.review_package.cine_export.CineReader', SyntheticReader)
        p.start(); self.addCleanup(p.stop)

    def cine(self, name, count=100):
        path = self.source / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(str(count))
        return path

    def scan(self, **kwargs):
        return scan_batch(self.source, self.output, 20, self.scheme, **kwargs)

    def test_recursive_discovery_mapping_unicode_and_metadata_only_scan(self):
        names = ['B/111.cine', 'C/222.CINE', 'B/sub/333.Cine', '高温实验/测试 01.cine', 'five.cine']
        for name in names: self.cine(name)
        (self.source/'empty').mkdir()
        self.cine('ignored.txt')
        self.assertEqual(len(discover_cines(self.source)), 5)
        plan = self.scan()
        self.assertEqual(SyntheticReader.reads, [])
        self.assertFalse(self.output.exists())
        for name in names:
            self.assertEqual(map_cine_to_package_path(str(self.source)+os.sep, self.output, self.source/name),
                             self.output/'A'/Path(name).with_suffix('.dvapkg'))
        before = {p.relative_to(self.source): (p.stat().st_size, p.stat().st_mtime_ns) for p in self.source.rglob('*')}
        result = execute_batch(plan)
        self.assertEqual((result.created, result.failed), (5, 0))
        self.assertEqual(SyntheticReader.peak_open, 1)
        self.assertEqual(SyntheticReader.open_count, 0)
        self.assertEqual(sum(i.frames_decoded for i in result.items), 105)
        self.assertFalse((self.output/'A/empty').exists())
        after = {p.relative_to(self.source): (p.stat().st_size, p.stat().st_mtime_ns) for p in self.source.rglob('*')}
        self.assertEqual(before, after)
        for name in names:
            package = AnnotationPackage.open(self.output/'A'/Path(name).with_suffix('.dvapkg'))
            cid = next(iter(package.documents))
            self.assertEqual(package.progress(cid), (20, 0, 20))
            self.assertEqual(package.manifest['sampling']['frame_indices'], uniform_frame_indices(100, 20))
            self.assertEqual(package.manifest['batch']['relative_source_path'], name)
            self.assertEqual(package.summary()['annotations'], 0)
            self.assertEqual(package.summary()['frame_states'], 0)
            self.assertTrue(all(i.source_unchanged for i in result.items))
        data = (self.output/'A/_batch_manifest.json').read_text(encoding='utf-8')
        self.assertNotIn(str(self.root), data)
        self.assertEqual(json.loads(data)['created'], 5)

    def test_source_output_safety_and_drive_root(self):
        path = self.cine('B/111.cine')
        for output in (self.source, self.source/'packages', self.source.parent):
            with self.assertRaises(ValueError): scan_batch(self.source, output, 20, self.scheme)
        with self.assertRaises(ValueError):
            map_cine_to_package_path(self.source.anchor, self.output, path)
        with self.assertRaises(ValueError):
            map_cine_to_package_path(self.source, self.output, self.root/'outside.cine')

    def test_short_cine_context_and_same_writer_raw_time64_photo(self):
        path = self.cine('short.cine', 12)
        result = execute_batch(self.scan(context=5))
        self.assertEqual(result.items[0].status, 'shortened_to_all_frames')
        batch = AnnotationPackage.open(self.output/'A/short.dvapkg')
        self.assertEqual(batch.manifest['sampling']['frame_indices'], list(range(12)))
        single = export_uniform_cine(path, self.root/'single.dvapkg', 20, self.scheme, context=5, allow_short=True)
        single = AnnotationPackage.open(self.root/'single.dvapkg')
        self.assertEqual(batch.frames, single.frames)
        self.assertEqual(batch.manifest['frames'], single.manifest['frames'])
        self.assertEqual(batch.manifest['photometric'], single.manifest['photometric'])
        self.assertEqual(batch.scheme, single.scheme)
        self.cine('long.cine', 1000)
        result = execute_batch(self.scan(context=5))
        long = AnnotationPackage.open(self.output/'A/long.dvapkg')
        self.assertEqual(long.summary()['target_frames'], 20)
        self.assertGreater(long.summary()['context_frames'], 0)
        self.assertEqual(len(long.manifest['frames']), len({f['frame_index'] for f in long.manifest['frames']}))

    def test_existing_policy_skip_overwrite_report_resume(self):
        self.cine('one.cine')
        plan = self.scan()
        self.assertEqual(plan.existing_policy, 'skip')
        execute_batch(plan)
        path = self.output/'A/one.dvapkg'
        original = path.read_bytes()
        for policy, status in [('skip', 'SKIPPED_EXISTING'), ('report_conflict', 'CONFLICT')]:
            SyntheticReader.reads.clear()
            result = execute_batch(self.scan(existing_policy=policy))
            self.assertEqual(result.items[0].status, status)
            self.assertEqual(path.read_bytes(), original)
            self.assertFalse(SyntheticReader.reads)
        result = execute_batch(self.scan(existing_policy='overwrite'))
        self.assertEqual(result.created, 1)
        self.assertNotEqual(path.read_bytes(), original)
        AnnotationPackage.open(path)

    def test_failure_isolation_and_same_stem_collision(self):
        self.cine('a.cine'); self.cine('b.cine'); self.cine('c.cine')
        plan = self.scan()
        original = SyntheticReader.read_frame
        def read(reader, index):
            if reader.path.name == 'b.cine': raise OSError('Corrupt synthetic Cine')
            return original(reader, index)
        with patch.object(SyntheticReader, 'read_frame', read):
            result = execute_batch(plan)
        self.assertEqual((result.created, result.failed), (2, 1))
        self.assertFalse((self.output/'A/b.dvapkg').exists())
        self.assertTrue((self.output/'A/c.dvapkg').exists())
        # On case-sensitive filesystems both names can coexist; always detect
        # case-folded destination collisions before any writer runs.
        with patch('droplet_vision.review_package.batch.discover_cines', return_value=[self.source/'a.cine']*2):
            collision = self.scan()
        self.assertTrue(all(i.status == 'FAILED' for i in collision.items))

    def test_cancel_keeps_completed_and_removes_writer_temp(self):
        for name in ('a.cine', 'b.cine', 'c.cine'): self.cine(name)
        cancel = Event()
        def check():
            if cancel.is_set(): raise BatchCancelled()
        def progress(event):
            if event['phase'] == 'item_done' and event['index'] == 2: cancel.set()
        result = execute_batch(self.scan(), checkpoint=check, progress=progress)
        self.assertTrue(result.cancelled)
        self.assertEqual(result.created, 2)
        self.assertFalse((self.output/'A/c.dvapkg').exists())
        # Cancel while ZIP is being written, preserving overwrite target.
        old = (self.output/'A/a.dvapkg').read_bytes()
        cancel.clear()
        original = zipfile.ZipFile.writestr
        def writing(archive, *args, **kwargs):
            value = original(archive, *args, **kwargs)
            cancel.set()
            return value
        with patch.object(zipfile.ZipFile, 'writestr', writing):
            result = execute_batch(self.scan(existing_policy='overwrite'), checkpoint=check)
        self.assertTrue(result.cancelled)
        self.assertEqual((self.output/'A/a.dvapkg').read_bytes(), old)
        self.assertEqual(list(self.output.rglob('.review-*')), [])

    def test_source_changes_fail_and_preserve_existing_package(self):
        path = self.cine('a.cine')
        self.cine('b.cine')
        execute_batch(self.scan())
        destination = self.output/'A/a.dvapkg'
        old = destination.read_bytes()
        plan = self.scan(existing_policy='overwrite')
        def progress(event):
            if event['phase'] == 'create' and event['source'] == 'a.cine':
                path.write_text('101')
        result = execute_batch(plan, progress=progress)
        self.assertEqual(result.failed, 1)
        self.assertFalse(result.items[0].source_unchanged)
        self.assertTrue(result.items[1].source_unchanged)
        self.assertEqual(destination.read_bytes(), old)
        plan = self.scan()
        path.write_text('102')
        result = execute_batch(plan)
        self.assertFalse(result.items[0].source_unchanged)
        self.assertEqual(result.items[0].status, 'FAILED')

    def test_scan_failures_empty_tree_and_invalid_settings(self):
        self.cine('bad.cine', 'corrupt')
        plan = self.scan()
        self.assertEqual(plan.items[0].status, 'FAILED')
        self.assertEqual(execute_batch(plan).failed, 1)
        with self.assertRaises(ValueError): self.scan(existing_policy='unknown')
        empty = self.root/'Empty'; empty.mkdir()
        result = execute_batch(scan_batch(empty, self.output, 20, self.scheme))
        self.assertEqual(result.created, 0)
