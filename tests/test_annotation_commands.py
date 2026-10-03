import sys
from pathlib import Path
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from droplet_vision.annotations import AnnotationDocument, AnnotationRecord
try:
    from PySide6.QtGui import QUndoStack
    from droplet_vision.ui.annotation_commands import AddAnnotationCommand, EditAnnotationCommand, DeactivateAnnotationCommand
    QT = True
except ImportError:
    QT = False


@unittest.skipUnless(QT, 'Optional Qt unavailable')
class CommandTests(unittest.TestCase):
    def test_add_edit_delete_undo_redo_preserves_every_record(self):
        doc = AnnotationDocument('fake', 'fake.cine', 100, 10, 256, 256)
        stack = QUndoStack()
        initial = AnnotationRecord('fake', 0, 'any_label', 'point', {'point': [50, 50]})
        stack.push(AddAnnotationCommand(doc, initial))
        derived = doc.derive(initial.annotation_id, {'point': [60, 60]})
        stack.push(EditAnnotationCommand(doc, initial.annotation_id, derived, 'manual'))
        stack.push(DeactivateAnnotationCommand(doc, derived.annotation_id))
        self.assertFalse(doc.active_records())
        stack.undo()
        self.assertEqual(doc.active_annotation_ids, {derived.annotation_id})
        stack.undo()
        self.assertEqual(doc.active_annotation_ids, {initial.annotation_id})
        stack.undo()
        self.assertFalse(doc.active_records())
        self.assertEqual(len(doc.records.records()), 2)
        stack.redo()
        stack.redo()
        self.assertEqual(doc.active_annotation_ids, {derived.annotation_id})
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'annotations.json'
            doc.save(path)
            stack.undo()
            self.assertTrue(doc.dirty)
            stack.redo()
            # Even restoring the same active view leaves new audit history unsaved.
            self.assertTrue(doc.dirty)
            doc.save(path)
            restored = AnnotationDocument.load(path)
            self.assertEqual(restored.active_annotation_ids, doc.active_annotation_ids)
            self.assertEqual(len(restored.records.records()), 2)
