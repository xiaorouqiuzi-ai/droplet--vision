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
from .frame_state import FrameStateRecord


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
        self._frame_states = {}
        self._active_frame_states = {}
        self.scheme = {}
        self._cine_templates = {}
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
        if original.source == 'imported' and original.attributes.get('creation_tool') == 'cine_template_projection':
            values['attributes']['creation_tool'] = 'cine_support_template_override'
        derived = AnnotationRecord.from_dict(values)
        self.validate_record(derived)
        return derived

    def active_records(self, frame_index: Optional[int] = None):
        return [r for r in self.records.records() if r.annotation_id in self._active
                and (frame_index is None or r.frame_index == frame_index)]

    def annotated_frames(self):
        return sorted({r.frame_index for r in self.active_records()} | set(self._active_frame_states))

    @property
    def cine_templates(self):
        return _json_copy(self._cine_templates)

    def _validate_templates(self, value):
        value = _json_copy(value)
        if not isinstance(value, dict) or set(value) - {'support_structure'}:
            raise ValueError('Invalid Cine template metadata')
        for template in value.values():
            if not isinstance(template, dict):
                raise ValueError('Invalid support rod template')
            if type(template.get('apply_entire_cine', False)) is not bool:
                raise ValueError('apply_entire_cine must be boolean')
            frame, ids = template.get('source_frame_index'), template.get('annotation_ids')
            if (type(frame) is not int or not 0 <= frame < self.frame_count
                    or not isinstance(ids, list) or not ids
                    or not all(isinstance(key, str) for key in ids) or len(set(ids)) != len(ids)):
                raise ValueError('Invalid support rod template source')
            for key in ids:
                if key not in self.record_layers:
                    raise ValueError('Missing support rod template record')
                record = self.records.get(key)
                if (record.frame_index != frame or record.label_id != 'support_structure'
                        or record.geometry_type != 'polygon' or record.source != 'manual'):
                    raise ValueError('Template requires confirmed manual support rod polygons')
        return value

    def replace_cine_templates(self, value):
        """Explicit template update/undo; edits to source records never call this."""
        self._cine_templates = self._validate_templates(value)
        self._touch('cine_templates', templates=self.cine_templates)

    def support_template_from(self, annotation_ids):
        ids = list(annotation_ids)
        if not ids or not set(ids) <= self.active_annotation_ids:
            raise ValueError('Select confirmed active support rod polygons')
        frame = self.records.get(ids[0]).frame_index
        return self._validate_templates({'support_structure': {
            'source_frame_index': frame, 'annotation_ids': ids}})

    def support_copies(self, frame_index):
        return [r for r in self.active_records(frame_index)
                if r.label_id == 'support_structure'
                and r.attributes.get('creation_tool') in (
                    'cine_support_template', 'cine_support_template_override', 'cine_template_projection')]

    def support_projection(self, source_id, frame_index, package=False):
        """Independent transient view, never inserted into this document's store.

        Package snapshots use deterministic, frame-specific IDs; viewer IDs are
        stable across frames so session visibility can hide one template rod.
        """
        from uuid import uuid5, NAMESPACE_URL
        source = self.records.get(source_id)
        if source.label_id != 'support_structure' or source.geometry_type != 'polygon' or source.source != 'manual':
            raise ValueError('Invalid support projection source')
        row = AnnotationRecord(self.cine_id, frame_index, 'support_structure', 'polygon',
                               _json_copy(source.geometry), source='imported' if package else 'manual',
                               annotation_id=(str(uuid5(NAMESPACE_URL, f'{self.document_id}:{source_id}:{frame_index}:support-projection'))
                                              if package else 'cine-template:' + source_id),
                               created_at=source.created_at, updated_at=source.updated_at,
                               attributes={'creation_tool': 'cine_template_projection',
                                           'template_source_annotation_id': source_id,
                                           'template_source_frame_index': source.frame_index,
                                           'instance_name': source.attributes.get('instance_name', '')})
        self.validate_record(row)
        return row

    def support_projections(self, frame_index, package=False):
        template = self._cine_templates.get('support_structure', {})
        if not template.get('apply_entire_cine', False):
            return []
        active = self.active_records(frame_index)
        replaced = {r.attributes.get('template_source_annotation_id') for r in self.support_copies(frame_index)}
        # A same-frame derived edit of a source also takes precedence.
        for record in active:
            key = record.annotation_id
            while key:
                replaced.add(key)
                key = self.records.get(key).derived_from
        return [self.support_projection(key, frame_index, package) for key in template['annotation_ids']
                if key not in replaced]

    def make_support_copies(self, frame_index, attributes=None):
        """Build independent records; caller commits the batch via Undo commands."""
        if type(frame_index) is not int or not 0 <= frame_index < self.frame_count:
            raise ValueError('Invalid target frame')
        template = self._cine_templates.get('support_structure')
        if template is None:
            raise ValueError('No Cine support rod template')
        copied = {r.attributes.get('template_source_annotation_id') for r in self.support_copies(frame_index)}
        result = []
        for number, key in enumerate(template['annotation_ids'], 1):
            if key in copied:
                continue
            original = self.records.get(key)
            values = _json_copy(attributes or {})
            values.update(instance_name=original.attributes.get('instance_name') or f'SupportRod_{number:02d}',
                          creation_tool='cine_support_template', template_source_annotation_id=key,
                          template_source_frame_index=template['source_frame_index'])
            record = AnnotationRecord(self.cine_id, frame_index, 'support_structure', 'polygon',
                                      _json_copy(original.geometry), source='manual', attributes=values)
            self.validate_record(record)
            result.append(record)
        return result

    @property
    def frame_state_records(self):
        return tuple(self._frame_states.values())

    @property
    def active_frame_state_records(self):
        return dict(self._active_frame_states)

    def frame_state(self, frame_index):
        return self._frame_states.get(self._active_frame_states.get(frame_index))

    def add_frame_state(self, record):
        if (record.record_id in self._frame_states or record.cine_id != self.cine_id
                or not 0 <= record.frame_index < self.frame_count):
            raise ValueError('Invalid or duplicate frame state identity')
        if record.derived_from is not None:
            parent = self._frame_states.get(record.derived_from)
            if parent is None or parent.frame_index != record.frame_index:
                raise ValueError('Invalid frame state history')
        self._frame_states[record.record_id] = record
        self._touch('add_frame_state', record_id=record.record_id)

    def activate_frame_state(self, frame_index, record_id):
        if type(frame_index) is not int or not 0 <= frame_index < self.frame_count:
            raise ValueError('Invalid frame state frame index')
        if record_id is None:
            self._active_frame_states.pop(frame_index, None)
        else:
            record = self._frame_states.get(record_id)
            if record is None or record.frame_index != frame_index:
                raise ValueError('Invalid active frame state pointer')
            self._active_frame_states[frame_index] = record_id
        self._touch('active_frame_state', frame_index=frame_index, record_id=record_id)

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
            "scheme": self.scheme,
            **({'cine_templates': self.cine_templates} if self._cine_templates else {}),
            "frame_state_records": [r.to_dict() for r in self.frame_state_records],
            "active_frame_state_records": {str(k): v for k, v in self._active_frame_states.items()},
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
        doc._cine_templates = doc._validate_templates(value.get('cine_templates', {}))
        doc.document_id = value["document_id"]
        doc.created_at, doc.updated_at = value["created_at"], value["updated_at"]
        doc.history = []
        doc.scheme = value.get('scheme', {})
        if doc.scheme:
            from .scheme import validate_scheme
            doc.scheme = validate_scheme(doc.scheme)
        # Optional extensions retain compatibility with documents written before v1.3.
        for row in value.get('frame_state_records', []):
            doc.add_frame_state(FrameStateRecord.from_dict(row))
        for index, record_id in value.get('active_frame_state_records', {}).items():
            if str(int(index)) != index or not isinstance(record_id, str) or not record_id:
                raise ValueError('Noncanonical frame state index')
            doc.activate_frame_state(int(index), record_id)
        doc.history = value.get('history', [])
        doc.updated_at = value['updated_at']
        doc._revision = doc._saved_revision = 0
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
