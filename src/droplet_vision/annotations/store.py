"""Append-only record store. Review creates a new record, never overwrites prediction."""
from __future__ import annotations
import json
from pathlib import Path
from typing import Dict, List, Optional, Any, Union
from .schema import AnnotationRecord, _now
from uuid import uuid4


class AnnotationStore:
    def __init__(self):
        self._records: Dict[str, AnnotationRecord] = {}

    def add(self, record: AnnotationRecord) -> None:
        if record.annotation_id in self._records:
            raise ValueError("Record ID already exists; create a derived record instead")
        self._records[record.annotation_id] = AnnotationRecord.from_dict(record.to_dict())

    def get(self, annotation_id: str) -> AnnotationRecord:
        return AnnotationRecord.from_dict(self._records[annotation_id].to_dict())

    def records(self) -> List[AnnotationRecord]:
        return [self.get(key) for key in self._records]

    def review(self, annotation_id: str, status: str, reviewer: str,
               geometry: Optional[Dict[str, Any]] = None) -> AnnotationRecord:
        if status not in ("accepted", "edited", "rejected", "ground_truth"):
            raise ValueError("Invalid review decision")
        original = self.get(annotation_id)
        values = original.to_dict()
        values.update(annotation_id=str(uuid4()), source="manual", model_id=None, confidence=None,
                      derived_from=annotation_id, reviewer=reviewer, review_status=status,
                      created_at=_now(), updated_at=_now())
        if geometry is not None:
            values["geometry"] = geometry
        derived = AnnotationRecord.from_dict(values)
        self.add(derived)
        return self.get(derived.annotation_id)

    def save(self, path: Union[str, Path]) -> None:
        path = Path(path)
        if path.suffix.lower() != ".json" or path.resolve().suffix.lower() != ".json":
            raise ValueError("Annotation destination must be a .json file")
        Path(path).write_text(json.dumps({"schema_version": 1, "records": [r.to_dict() for r in self.records()]},
                                         indent=2, allow_nan=False), encoding="utf-8")

    @classmethod
    def load(cls, path: Union[str, Path]) -> AnnotationStore:
        value = json.loads(Path(path).read_text(encoding="utf-8"))
        if value["schema_version"] != 1:
            raise ValueError("Unsupported annotation store version")
        store = cls()
        for record in value["records"]:
            store.add(AnnotationRecord.from_dict(record))
        return store
