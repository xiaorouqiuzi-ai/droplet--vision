"""Atomic, resumable JSON queues. The dataset root exists only at runtime."""
from __future__ import annotations
import json
import os
from pathlib import Path
import tempfile
from uuid import uuid4
from .schema import AnnotationQueueItem, STATUSES, now, relative_path


def atomic_json(path, value) -> None:
    path = Path(path)
    if path.suffix.lower() != ".json" or path.resolve().suffix.lower() != ".json":
        raise ValueError("Queue output must be JSON")
    payload = json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(payload + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


class AnnotationQueue:
    schema_version = 1

    def __init__(self, name, sampling_preset_id, dataset_root_hint, items=(), sampling_config=None):
        relative_path(dataset_root_hint)
        if "/" in dataset_root_hint:
            raise ValueError("Dataset root hint must be a name, not a path")
        self.queue_id = str(uuid4())
        self.name, self.sampling_preset_id = name, sampling_preset_id
        self.dataset_root_hint = dataset_root_hint
        self.created_at = self.updated_at = now()
        self.items = list(items)
        if len({i.item_id for i in self.items}) != len(self.items):
            raise ValueError("Duplicate queue items")
        self.sampling_config = sampling_config or {}
        self.failed_files = []
        self.sampling_report = []
        self.dirty = False

    def get(self, item_id):
        return next(item for item in self.items if item.item_id == item_id)

    @property
    def done_count(self):
        return sum(item.status == "DONE" for item in self.items)

    def update(self, item_id, *, status=None, notes=None):
        item = self.get(item_id)
        if status is not None:
            if status not in STATUSES:
                raise ValueError("Invalid queue status")
            item.status = status
        if notes is not None:
            if not isinstance(notes, str):
                raise ValueError("Notes must be text")
            item.notes = notes
        item.updated_at = self.updated_at = now()
        self.dirty = True

    def link_document(self, cine_path, reference):
        relative_path(reference)
        for item in self.items:
            if item.relative_cine_path == cine_path:
                item.annotation_document = reference
                item.updated_at = now()
        self.updated_at = now()
        self.dirty = True

    def resume_from(self, previous):
        """Preserve human decisions; reject changed sampling or source identities."""
        if self.sampling_config != previous.sampling_config:
            raise ValueError("Existing queue uses a different sampling configuration")
        old = {i.item_id: i for i in previous.items}
        if not set(old) <= {i.item_id for i in self.items}:
            raise ValueError("Rebuild would lose existing queue items; use a new output path")
        for item in self.items:
            if item.item_id in old:
                before = old[item.item_id]
                if (before.frame_count, before.cine_file_size, before.cine_mtime_ns) != (item.frame_count, item.cine_file_size, item.cine_mtime_ns):
                    raise ValueError("Source identity changed since existing queue")
                for key in ("status", "notes", "annotation_document", "created_at", "updated_at"):
                    setattr(item, key, getattr(before, key))
        self.queue_id, self.created_at = previous.queue_id, previous.created_at

    def to_dict(self):
        return {"schema_version": self.schema_version, "queue_id": self.queue_id, "name": self.name,
                "sampling_preset_id": self.sampling_preset_id, "dataset_root_hint": self.dataset_root_hint,
                "created_at": self.created_at, "updated_at": self.updated_at,
                "sampling_config": self.sampling_config, "items": [i.to_dict() for i in self.items],
                "failed_files": self.failed_files, "sampling_report": self.sampling_report}

    @classmethod
    def from_dict(cls, value):
        if value["schema_version"] != cls.schema_version:
            raise ValueError("Unsupported queue schema")
        queue = cls(value["name"], value["sampling_preset_id"], value["dataset_root_hint"],
                    [AnnotationQueueItem(**row) for row in value["items"]], value["sampling_config"])
        for key in ("queue_id", "created_at", "updated_at", "failed_files", "sampling_report"):
            setattr(queue, key, value[key])
        return queue

    def save(self, path):
        atomic_json(path, self.to_dict())
        self.dirty = False

    @classmethod
    def load(cls, path):
        return cls.from_dict(json.loads(Path(path).read_text(encoding="utf-8")))
