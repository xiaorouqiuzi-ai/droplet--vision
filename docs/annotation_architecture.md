# Annotation architecture

The Qt-free `annotations` package separates scientific observation records from
Viewer UI state. See [Annotation Editor v1](annotation_editor.md) for operations.

- `AnnotationRecord`: an open `label_id`, geometry, source/review provenance and
  optional `derived_from`. Store insertion makes a defensive JSON-safe copy.
- `AnnotationStore`: append-only historical records. Reads return copies;
  neither editing nor undo physically replaces/removes a stored record.
- `AnnotationDocument`: portable Cine identity, dimensions, taxonomy metadata,
  store, `active_annotation_ids`, deactivated IDs, fixed record layer membership,
  timestamps and audit events. Active IDs determine the current visible data.
- `ViewerSession`: navigation, bookmarks, notes and display state only. It does
  not embed annotation records or serve as the scientific annotation document.
- `ui.annotation_commands`: actual QUndoCommand add/edit/deactivate operations
  managed by QUndoStack. Undo/redo changes active IDs and appends audit events.
- `ui.annotation_editor` and registry-based tools: temporary geometry, selection,
  editor handles, label/layer policy, save/load and dirty-state protection.
  Base OverlayManager remains a geometry renderer, separate from edit handles.

## JSON document schema v1

```json
{
  "schema_version": 1,
  "document_id": "uuid",
  "cine": {
    "cine_id": "sample", "filename": "sample.cine",
    "file_size_bytes": 100, "frame_count": 1000,
    "width": 256, "height": 256
  },
  "taxonomy": {"reference": "default_taxonomy.json", "labels": []},
  "active_annotation_ids": [],
  "deactivated_annotation_ids": [],
  "record_layers": {},
  "records": [],
  "created_at": "ISO-8601 timestamp",
  "updated_at": "ISO-8601 timestamp",
  "history": []
}
```

Active and deactivated sets partition every stored record ID. `record_layers`
maps each immutable record ID to a layer ID. Loading rejects invalid geometry,
unknown active IDs, duplicate records, cross-frame derivations and history cycles.
No absolute Cine path, raw image array or Cine copy is stored. Formal JSON and
autosave use same-directory temporary files, fsync and atomic replace.

Manual edit creates a manual/edited derivative, deactivates its parent and
activates the new ID. Model edit uses the same lineage and creates a Reviewed
derivative without altering original model geometry, confidence or model ID.
Inactive history is included on save. Ground Truth derivation is supported at
the document layer; no irreversible approval UI is added.

Geometry always uses raw pixel coordinates and is independent of display.
TIME64 and relative time provenance live in record attributes without changing
the core record schema. Display mode may be recorded as review context, never
as geometry or a scientific-intensity source. Labels are loaded from taxonomy;
the UI does not use ObjectType as a closed annotation vocabulary.
