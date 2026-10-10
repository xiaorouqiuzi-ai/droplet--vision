"""Queue workflow coordinates existing asynchronous Cine and annotation APIs."""
from __future__ import annotations
from .i18n import tr
import hashlib
from pathlib import Path
from ..resources import output_path
from PySide6.QtCore import QObject, Qt
from PySide6.QtWidgets import QDockWidget, QFileDialog, QInputDialog
from ..sampling import AnnotationQueue
from ..sampling.schema import resolve_relative
from ..sampling.sampler import outside_source
from ..annotations import AnnotationDocument
from .panels.queue_panel import QueuePanel


class QueueCoordinator(QObject):
    def __init__(self, window):
        super().__init__(window)
        self.window = window
        self.queue = self.path = self.root = None
        self.current_id = None
        self.pending = None
        self.unavailable = {}
        self._initiating = False
        self.panel = QueuePanel()
        self.dock = QDockWidget(tr("Annotation Queue"), window)
        self.dock.setObjectName("annotationQueueDock")
        self.dock.setWidget(self.panel)
        window.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self.dock)
        self.dock.hide()  # existing editor workspace remains usable until a queue is opened
        menu = window.menuBar().addMenu(tr("Queue"))
        menu.addAction(self.dock.toggleViewAction())
        actions = {"open_queue": self.open_dialog, "set_root": self.root_dialog,
                   "open_item": self.open_selected, "next": lambda: self.pending_item(1),
                   "previous": lambda: self.pending_item(-1), "done": lambda: self.mark("DONE"),
                   "skipped": lambda: self.mark("SKIPPED"), "review": lambda: self.mark("NEEDS_REVIEW"),
                   "note": self.note_dialog, "save": self.save}
        for key, button in self.panel.buttons.items():
            window._action(menu, button.text(), actions[key])
        self.panel.requested.connect(lambda key: actions[key]())
        window.cine_open_requested.connect(self.external_open)
        window.controller.closed.connect(self.on_closed)
        window.controller.opened.connect(self.on_opened)
        window.controller.frame_ready.connect(self.on_frame)
        window.controller.failed.connect(self.on_failure)
        window.editor.saved.connect(self.document_saved)

    def refresh(self):
        if self.queue is not None:
            self.panel.show_queue(self.queue, self.current_id, self.unavailable)

    def save(self):
        if self.queue is None:
            return True
        try:
            if self.root is not None:
                outside_source(self.path, self.root)
            self.queue.save(self.path)
        except Exception as error:
            self.window._error(tr("Queue save failed; changes remain in memory: ") + str(error))
            self.refresh()
            return False
        self.refresh()
        return True

    def confirm_close(self):
        return self.queue is None or not self.queue.dirty or self.save()

    def load(self, path, root=None):
        queue = AnnotationQueue.load(path)
        path = Path(path).resolve()
        if root is not None:
            outside_source(path, root)
        if not self.confirm_close():
            return False
        self.queue, self.path = queue, path
        self.root = None
        self.panel.root_label.setText(tr("Dataset root: not set (local only)"))
        self.current_id = self.pending = None
        self.unavailable = {}
        if root is not None:
            self.set_root(root)
        self.refresh()
        self.dock.show()
        return True

    def set_root(self, root):
        root = Path(root).resolve()
        if not root.is_dir():
            raise NotADirectoryError(root)
        if self.path is not None:
            outside_source(self.path, root)
        self.root = root
        self.pending = self.current_id = None
        self.unavailable = {}
        if self.queue is not None:
            for item in self.queue.items:
                try:
                    if not resolve_relative(root, item.relative_cine_path).is_file():
                        self.unavailable[item.item_id] = tr("Cine file not found")
                except ValueError as error:
                    self.unavailable[item.item_id] = str(error)
        self.panel.root_label.setText(tr("Dataset root: ") + root.name + " (local only)")
        self.refresh()

    def open_dialog(self):
        path, _ = QFileDialog.getOpenFileName(self.window, tr("Open Annotation Queue"), str(output_path('annotation_queues')), tr("Queue JSON (*.json)"))
        if path:
            try:
                if self.load(path):
                    self.root_dialog()
            except Exception as error:
                self.window._error(str(error))

    def root_dialog(self):
        root = QFileDialog.getExistingDirectory(self.window, tr("Select local dataset root"))
        if root:
            try:
                self.set_root(root)
            except Exception as error:
                self.window._error(str(error))

    def external_open(self, path):
        if not self._initiating:
            self.pending = self.current_id = None
            self.refresh()

    def on_closed(self):
        self.pending = self.current_id = None
        self.refresh()

    def on_failure(self, message):
        if self.pending is not None:
            self.unavailable[self.pending[0]] = message
        self.pending = None
        self.refresh()

    def open_selected(self):
        item_id = self.panel.selected_id()
        return self.open_item(item_id) if item_id else False

    def open_item(self, item_id):
        if self.queue is None or self.root is None:
            self.window.statusBar().showMessage(tr("Open a queue and set its local dataset root first."))
            return False
        item = self.queue.get(item_id)
        try:
            path = resolve_relative(self.root, item.relative_cine_path)
            stat = path.stat()
            if item.cine_file_size is not None and (stat.st_size, stat.st_mtime_ns) != (item.cine_file_size, item.cine_mtime_ns):
                raise ValueError("Cine size/mtime differs from sampling provenance")
            if item.annotation_document is not None:
                linked = resolve_relative(self.path.parent, item.annotation_document)
                outside_source(linked, self.root)
                if not linked.is_file():
                    raise FileNotFoundError(tr("Linked AnnotationDocument is unavailable"))
        except Exception as error:
            self.unavailable[item_id] = str(error)
            self.refresh()
            self.window._error(tr("Queue item unavailable: ") + str(error))
            return False
        self.window.pause()
        same = self.window.cine_path is not None and self.window.cine_path.resolve() == path and self.window.metadata is not None
        if same:
            editor = self.window.editor
            if not editor.confirm_discard():
                return False
            # A same-Cine queue switch also honors explicit Discard; ordinary frame
            # navigation never discards. Preserve the last formally saved document.
            if editor.document is not None and editor.document.dirty:
                try:
                    restored = AnnotationDocument.load(editor.path) if editor.path else None
                except Exception as error:
                    self.window._error(tr("Could not restore saved annotations: ") + str(error))
                    return False
                if restored is None:
                    editor._create_document()
                else:
                    editor.document = restored
                    editor.selected_id = None
                    editor.undo_stack.clear()
                    editor.changed()
            self.pending = (item_id, path, False)
            self.window.navigate(item.frame_index)
        else:
            before = self.pending
            self._initiating = True
            try:
                self.pending = (item_id, path, True)
                if not self.window.open_cine(path):
                    self.pending = before
                    return False
            finally:
                self._initiating = False
        self.unavailable.pop(item_id, None)
        return True

    def on_opened(self, metadata, timing):
        if self.pending is not None:
            item = self.queue.get(self.pending[0])
            if metadata.frame_count != item.frame_count or metadata.filename != item.cine_filename:
                self.on_failure(tr("Cine identity does not match queue"))
                self.window._error(tr("Cine identity does not match queue"))
                return
            self.window.navigate(item.frame_index)

    def on_frame(self, index, image, record):
        if self.pending is None:
            return
        item_id, path, changed_cine = self.pending
        item = self.queue.get(item_id)
        if (self.window.cine_path is None or self.window.cine_path.resolve() != path
                or self.window.current_record is not record or index != item.frame_index):
            return
        self.pending = None
        try:
            if item.annotation_document is not None and (changed_cine or self.window.editor.path is None):
                if not self.window.editor.load(resolve_relative(self.path.parent, item.annotation_document)):
                    return
        except Exception as error:
            self.unavailable[item_id] = str(error)
            self.refresh()
            self.window._error(tr("Queue annotation load failed: ") + str(error))
            return
        self.current_id = item_id
        if item.status == "PENDING":
            self.queue.update(item_id, status="IN_PROGRESS")
            self.save()
        self.refresh()
        for row in range(self.panel.items.count()):
            if self.panel.items.item(row).data(Qt.ItemDataRole.UserRole) == item_id:
                self.panel.items.setCurrentRow(row)
                break

    def pending_item(self, direction):
        if self.queue is None:
            return False
        ids = [i.item_id for i in self.queue.items]
        pivot = self.current_id or self.panel.selected_id()
        index = ids.index(pivot) if pivot in ids else (-1 if direction > 0 else len(ids))
        for offset in range(index+direction, len(ids) if direction > 0 else -1, direction):
            item = self.queue.items[offset]
            if item.status == "PENDING" and item.item_id not in self.unavailable:
                return self.open_item(item.item_id)
        self.window.statusBar().showMessage(tr("No pending item in that direction; select an IN_PROGRESS item to resume it."))
        return False

    def mark(self, status):
        # Explicit human action; cannot mark a different selected row by accident.
        if self.current_id is None or self.pending is not None:
            return False
        item = self.queue.get(self.current_id)
        record = self.window.current_record
        if record is None or record.frame_index != item.frame_index or self.window.cine_path.resolve() != resolve_relative(self.root, item.relative_cine_path):
            self.window.statusBar().showMessage(tr("Open the queue item before marking its status."))
            return False
        self.queue.update(self.current_id, status=status)
        return self.save()

    def note_dialog(self):
        item_id = self.panel.selected_id() or self.current_id
        if self.queue is not None and item_id:
            text, ok = QInputDialog.getMultiLineText(self.window, tr("Queue note"), tr("Manual note"), self.queue.get(item_id).notes)
            if ok:
                self.queue.update(item_id, notes=text)
                self.save()

    def annotation_path(self):
        if self.queue is None or self.root is None or self.window.cine_path is None:
            return None
        try:
            relative = self.window.cine_path.resolve().relative_to(self.root).as_posix()
        except ValueError:
            return None
        matches = [i for i in self.queue.items if i.relative_cine_path == relative]
        if not matches:
            return None
        if matches[0].annotation_document:
            return resolve_relative(self.path.parent, matches[0].annotation_document)
        digest = hashlib.sha256(relative.encode()).hexdigest()[:16]
        return self.path.parent / "annotations" / (self.window.cine_path.stem + "_" + digest + ".annotations.json")

    def document_saved(self, path):
        if self.queue is None or self.root is None or self.window.cine_path is None:
            return
        try:
            relative_cine = self.window.cine_path.resolve().relative_to(self.root).as_posix()
            reference = Path(path).resolve().relative_to(self.path.parent).as_posix()
        except ValueError:
            self.window.statusBar().showMessage(tr("Annotation saved; queue links require a document inside the queue folder."))
            return
        self.queue.link_document(relative_cine, reference)
        self.save()
