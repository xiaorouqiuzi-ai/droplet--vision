"""QUndoStack commands change visibility, never erase immutable record history."""
from .i18n import tr
from PySide6.QtGui import QUndoCommand


class SetFrameStateCommand(QUndoCommand):
    def __init__(self, document, record, changed=lambda: None):
        super().__init__(tr('Set frame state'))
        self.document, self.record, self.changed = document, record, changed
        previous = document.frame_state(record.frame_index)
        self.previous_id = previous.record_id if previous else None
        self.added = False

    def redo(self):
        if not self.added:
            self.document.add_frame_state(self.record)
            self.added = True
        self.document.activate_frame_state(self.record.frame_index, self.record.record_id)
        self.changed()

    def undo(self):
        self.document.activate_frame_state(self.record.frame_index, self.previous_id)
        self.changed()


class AddAnnotationCommand(QUndoCommand):
    def __init__(self, document, record, layer_id="manual", changed=lambda: None):
        super().__init__(tr("Add ") + record.geometry_type)
        self.document, self.record, self.layer_id = document, record, layer_id
        self.changed = changed
        self.added = False

    def redo(self):
        if not self.added:
            self.document.add_record(self.record, self.layer_id)
            self.added = True
        else:
            self.document.transition(activate=[self.record.annotation_id], reason="redo_add")
        self.changed()

    def undo(self):
        self.document.transition(deactivate=[self.record.annotation_id], reason="undo_add")
        self.changed()


class EditAnnotationCommand(AddAnnotationCommand):
    def __init__(self, document, old_id, derived, layer_id, changed=lambda: None):
        super().__init__(document, derived, layer_id, changed)
        self.old_id = old_id
        self.setText(tr("Edit ") + derived.geometry_type)

    def redo(self):
        if not self.added:
            self.document.add_record(self.record, self.layer_id, activate=False)
            self.added = True
        self.document.transition(activate=[self.record.annotation_id], deactivate=[self.old_id], reason="edit")
        self.changed()

    def undo(self):
        self.document.transition(activate=[self.old_id], deactivate=[self.record.annotation_id], reason="undo_edit")
        self.changed()


class DeactivateAnnotationCommand(QUndoCommand):
    def __init__(self, document, annotation_id, changed=lambda: None):
        super().__init__(tr("Deactivate annotation"))
        self.document, self.annotation_id, self.changed = document, annotation_id, changed

    def redo(self):
        self.document.transition(deactivate=[self.annotation_id], reason="user_delete")
        self.changed()

    def undo(self):
        self.document.transition(activate=[self.annotation_id], reason="undo_delete")
        self.changed()
