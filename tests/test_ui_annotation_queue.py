import tempfile
from pathlib import Path
import unittest
from unittest.mock import patch
from test_ui_main_window import QT_AVAILABLE, wait_for
from test_ui_annotation_tools import EditorReader
from test_annotation_queue import item
from droplet_vision.sampling import AnnotationQueue

if QT_AVAILABLE:
    from PySide6.QtWidgets import QApplication, QMessageBox
    from droplet_vision.ui.main_window import MainWindow
    from droplet_vision.ui.cine_controller import CineController


class QueueReader(EditorReader):
    opens = []
    def __init__(self, path):
        super().__init__(path)
        self.path = Path(path)
        self.metadata.filename = self.path.name
        self.metadata.file_size_bytes = self.path.stat().st_size
        self.opens.append(self.path)

    def build_frame_result(self, index):
        record = super().build_frame_result(index)
        record.cine_id = self.path.stem
        return record


@unittest.skipUnless(QT_AVAILABLE, 'Optional Qt unavailable')
class QueueUiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        folder = Path(self.temp.name)
        self.root = folder/'dataset'
        self.root.mkdir()
        for name in ('a.cine', 'b.cine'):
            (self.root/name).write_bytes(b'test placeholder; mocked reader only')
        self.path = folder/'out/queue.json'
        self.items = [item(5, 'a.cine'), item(15, 'a.cine'), item(5, 'b.cine')]
        AnnotationQueue('synthetic queue', 'v1', 'dataset', self.items).save(self.path)
        QueueReader.opens = []
        self.window = MainWindow(Path(__file__).parent/'fixtures/experimental_taxonomy.json',
                                 controller=CineController(reader_factory=QueueReader))
        self.addCleanup(self.close)
        self.window.show()
        self.manager = self.window.queue_manager
        self.manager.load(self.path, self.root)

    def close(self):
        with patch.object(QMessageBox, 'warning', return_value=QMessageBox.StandardButton.Discard):
            self.window.close()

    def open_item(self, index):
        self.assertTrue(self.manager.open_item(self.items[index].item_id))
        wait_for(lambda: self.manager.current_id == self.items[index].item_id and self.manager.pending is None)

    def test_progress_status_persistence_and_same_cine_navigation(self):
        self.assertEqual(self.manager.panel.items.count(), 3)
        self.assertTrue(self.manager.pending_item(1))
        wait_for(lambda: self.manager.current_id == self.items[0].item_id)
        self.assertEqual(self.manager.queue.items[0].status, 'IN_PROGRESS')
        self.assertTrue(self.manager.mark('DONE'))
        self.assertEqual(self.manager.panel.progress.text(), '1 / 3 done')
        self.assertTrue(self.manager.pending_item(1))
        wait_for(lambda: self.manager.current_id == self.items[1].item_id)
        self.assertEqual(len(QueueReader.opens), 1)
        self.assertEqual(self.window.current_record.frame_index, 15)
        self.manager.mark('SKIPPED')
        self.open_item(2)
        self.assertEqual(len(QueueReader.opens), 2)
        self.manager.mark('NEEDS_REVIEW')
        saved = AnnotationQueue.load(self.path)
        self.assertEqual([i.status for i in saved.items], ['DONE', 'SKIPPED', 'NEEDS_REVIEW'])
        self.manager.load(self.path, self.root)
        self.assertEqual(self.manager.panel.progress.text(), '1 / 3 done')

    def test_dirty_cancel_blocks_same_and_different_item_save_links_shared_document(self):
        self.open_item(0)
        self.window.annotation_panel.labels.setCurrentRow(0)
        self.window.editor.create_annotation('polygon', {'points': [[10,10],[40,10],[40,40]]})
        with patch.object(QMessageBox, 'warning', return_value=QMessageBox.StandardButton.Cancel):
            self.assertFalse(self.manager.open_item(self.items[1].item_id))
            self.assertFalse(self.manager.open_item(self.items[2].item_id))
        self.assertEqual(self.manager.current_id, self.items[0].item_id)
        self.assertEqual(len(QueueReader.opens), 1)
        destination = self.window.editor.default_path()
        self.assertTrue(destination.is_relative_to(self.path.parent))
        self.window.editor.save(destination)
        self.assertEqual(self.manager.queue.items[0].annotation_document, self.manager.queue.items[1].annotation_document)
        self.open_item(2)
        self.open_item(1)
        self.assertEqual(len(self.window.editor.document.active_records()), 1)
        self.assertEqual(self.window.editor.document.active_records()[0].frame_index, 5)

    def test_missing_source_stale_open_and_manual_navigation_do_not_mark_wrong_item(self):
        (self.root/'b.cine').unlink()
        self.manager.set_root(self.root)
        self.assertIn(self.items[2].item_id, self.manager.unavailable)
        with patch.object(self.window, '_error'):
            self.assertFalse(self.manager.open_item(self.items[2].item_id))
        self.manager.open_item(self.items[0].item_id)
        self.manager.open_item(self.items[1].item_id)
        wait_for(lambda: self.manager.current_id == self.items[1].item_id)
        self.assertEqual(self.manager.queue.items[0].status, 'PENDING')
        self.window.navigate(30)
        wait_for(lambda: self.window.current_record.frame_index == 30)
        self.assertFalse(self.manager.mark('DONE'))

    def test_queue_save_failure_warns_retains_dirty_and_previous_pending(self):
        self.open_item(1)
        self.assertTrue(self.manager.pending_item(-1))
        wait_for(lambda: self.manager.current_id == self.items[0].item_id)
        with patch.object(self.manager.queue, 'save', side_effect=OSError('disk failure')), patch.object(self.window, '_error') as warning:
            self.assertFalse(self.manager.mark('NEEDS_REVIEW'))
            self.assertTrue(self.manager.queue.dirty)
            warning.assert_called_once()
        self.assertTrue(self.manager.save())
        self.assertFalse(self.manager.queue.dirty)
