"""Qt-free annotation document: immutable records, mutable active view, atomic JSON."""
from __future__ import annotations
import json
import os
from pathlib import Path, PureWindowsPath
import tempfile
from typing import Optional
from uuid import uuid4

from .geometry import validate_geometry
from .schema import AnnotationRecord, _json_copy, _now
from .store import AnnotationStore


class AnnotationDocument:
    schema_version = 1

    def __init__(self, cine_id: str, cine_filename: str, cine_file_size: int,
                 frame_count: int, width: int, height: int, taxonomy=None):
        if (not cine_id or not cine_filename or Path(cine_filename).name != cine_filename
                or PureWindowsPath(cine_filename).name != cine_filename
                or PureWindowsPath(cine_filename).drive or cine_filename in (".", "..")):
            raise ValueError("Cine identity must use a portable filename")
        if (any(isinstance(n, bool) or not isinstance(n, int) for n in (cine_file_size, frame_count, width, height))
                or cine_file_size < 0 or frame_count < 1 or width < 1 or height < 1):
            raise ValueError("Invalid Cine dimensions or identity")
        self.document_id = str(uuid4())
        self.cine_id, self.cine_filename = cine_id, cine_filename
        self.cine_file_size, self.frame_count = cine_file_size, frame_count
        self.width, self.height = width, height
        self.taxonomy = _json_copy(taxonomy or {})
        self.created_at = self.updated_at = _now()
        self.records = AnnotationStore()
        self._active = set()
        self.record_layers = {}
        self.history = []
        self._revision = self._saved_revision = 0

    @property
    def active_annotation_ids(self):
        return frozenset(self._active)

    @property
    def deactivated_annotation_ids(self):
        return frozenset(self.record_layers) - self.active_annotation_ids

    @property
    def dirty(self) -> bool:
        return self._revision != self._saved_revision

    def _touch(self, action, **details):
        self.updated_at = _now()
        self._revision += 1
        self.history.append({"action": action, "at": self.updated_at, **details})

    def validate_record(self, record):
        if (isinstance(record.frame_index, bool) or not isinstance(record.frame_index, int)
                or record.cine_id != self.cine_id or not 0 <= record.frame_index < self.frame_count):
            raise ValueError("Annotation does not match the document Cine/frame range")
        validate_geometry(record.geometry_type, record.geometry, self.width, self.height)

    def add_record(self, record: AnnotationRecord, layer_id: str = "manual", activate=True):
        self.validate_record(record)
        if not layer_id:
            raise ValueError("Layer ID is required")
        if record.derived_from is not None:
            parent = self.records.get(record.derived_from)
            if (parent.cine_id, parent.frame_index) != (record.cine_id, record.frame_index):
                raise ValueError("Derived record must preserve Cine and frame identity")
        self.records.add(record)
        self.record_layers[record.annotation_id] = layer_id
        if activate:
            self._active.add(record.annotation_id)
        self._touch("add", annotation_id=record.annotation_id, layer_id=layer_id, active=activate)

    def transition(self, activate=(), deactivate=(), reason="active_view"):
        activate, deactivate = set(activate), set(deactivate)
        if activate & deactivate or not (activate | deactivate) <= set(self.record_layers):
            raise ValueError("Invalid active annotation transition")
        self._active.difference_update(deactivate)
        self._active.update(activate)
        self._touch(reason, activated=sorted(activate), deactivated=sorted(deactivate))

    def derive(self, annotation_id: str, geometry=None, review_status="edited", reviewer=None):
        original = self.records.get(annotation_id)
        values = original.to_dict()
        values.update(annotation_id=str(uuid4()), derived_from=annotation_id, source="manual",
                      model_id=None, confidence=None, reviewer=reviewer, review_status=review_status,
                      created_at=_now(), updated_at=_now())
        if geometry is not None:
            values["geometry"] = _json_copy(geometry)
        derived = AnnotationRecord.from_dict(values)
        self.validate_record(derived)
        return derived

    def active_records(self, frame_index: Optional[int] = None):
        return [r for r in self.records.records() if r.annotation_id in self._active
                and (frame_index is None or r.frame_index == frame_index)]

    def annotated_frames(self):
        return sorted({r.frame_index for r in self.active_records()})

    def matches_cine(self, filename, size, frame_count, width, height):
        return (self.cine_filename, self.cine_file_size, self.frame_count, self.width, self.height) == (
            filename, size, frame_count, width, height)

    def to_dict(self):
        return _json_copy({
            "schema_version": self.schema_version, "document_id": self.document_id,
            "cine": {"cine_id": self.cine_id, "filename": self.cine_filename,
                     "file_size_bytes": self.cine_file_size, "frame_count": self.frame_count,
                     "width": self.width, "height": self.height},
            "taxonomy": self.taxonomy, "created_at": self.created_at, "updated_at": self.updated_at,
            "active_annotation_ids": sorted(self._active),
            "deactivated_annotation_ids": sorted(self.deactivated_annotation_ids),
            "record_layers": self.record_layers,
            "records": [r.to_dict() for r in self.records.records()], "history": self.history})

    @classmethod
    def from_dict(cls, value):
        value = _json_copy(value)
        if value["schema_version"] != cls.schema_version:
            raise ValueError("Unsupported annotation document schema version")
        cine = value["cine"]
        doc = cls(cine["cine_id"], cine["filename"], cine["file_size_bytes"],
                  cine["frame_count"], cine["width"], cine["height"], value["taxonomy"])
        for row in value["records"]:
            record = AnnotationRecord.from_dict(row)
            doc.validate_record(record)
            doc.records.add(record)
        ids = {r.annotation_id for r in doc.records.records()}
        active = value["active_annotation_ids"]
        deactivated = value["deactivated_annotation_ids"]
        layers = value["record_layers"]
        if (len(set(active)) != len(active) or len(set(deactivated)) != len(deactivated)
                or set(active) & set(deactivated) or set(active) | set(deactivated) != ids
                or set(layers) != ids or any(not isinstance(v, str) or not v for v in layers.values())):
            raise ValueError("Inconsistent annotation IDs or layer membership")
        for record in doc.records.records():
            ancestors = {record.annotation_id}
            current = record
            while current.derived_from is not None:
                if current.derived_from not in ids or current.derived_from in ancestors:
                    raise ValueError("Invalid derived annotation history")
                ancestors.add(current.derived_from)
                current = doc.records.get(current.derived_from)
                if current.frame_index != record.frame_index:
                    raise ValueError("Derived history crosses frame boundaries")
        doc._active = set(active)
        doc.record_layers = layers
        doc.document_id = value["document_id"]
        doc.created_at, doc.updated_at = value["created_at"], value["updated_at"]
        doc.history = value.get("history", [])
        return doc

    def save(self, path, mark_saved=True):
        path = Path(path)
        if path.suffix.lower() != ".json" or path.resolve().suffix.lower() != ".json":
            raise ValueError("Annotation destination must be a .json file")
        payload = json.dumps(self.to_dict(), indent=2, ensure_ascii=False, allow_nan=False)
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
        if mark_saved:
            self._saved_revision = self._revision

    @classmethod
    def load(cls, path):
        return cls.from_dict(json.loads(Path(path).read_text(encoding="utf-8")))
