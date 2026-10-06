# Annotation Architecture

Developer reference for implemented data contracts. Operations are documented in
[Annotation Editor](annotation_editor.md); scientific semantics live only in the
[labeling scheme](annotation_labeling_scheme_v1.md). The broader store boundaries
remain defined by [Data Architecture](data_architecture_concept_v1.md).

## Records, storage and active view

| Component | Contract |
| --- | --- |
| AnnotationRecord | Open string `label_id`, raw-coordinate geometry, source/review provenance and optional `derived_from` |
| AnnotationStore | Append-only defensive copies; reads cannot mutate stored records |
| AnnotationDocument | Cine identity/dimensions, Scheme/taxonomy snapshot, Object store, active IDs, State history/pointers and audit metadata |
| FrameStateRecord | Frozen frame-level judgment with state IDs, TIME64, quality, notes and lineage; no geometry |
| AnnotationLayer | Visible/locked presentation role; does not replace history ownership |
| ViewerSession | UI/navigation/bookmark/display state only, never the annotation database |

An AnnotationRecord dataclass is a transport value, not intrinsically immutable.
Immutability is enforced by store insertion/copy semantics and derived editing.
`active_annotation_ids` and `deactivated_annotation_ids` partition stored IDs;
`record_layers` assigns each record's layer. Delete deactivates, never erases.

## Document JSON v1

The current `schema_version=1` includes backward-compatible optional State/Scheme
keys. This structural example omits record bodies:

```json
{
  "schema_version": 1,
  "document_id": "example-document-id",
  "cine": {
    "cine_id": "sample", "filename": "sample.cine",
    "file_size_bytes": 100, "frame_count": 1000, "width": 256, "height": 256
  },
  "taxonomy": {"reference": "default_taxonomy.json", "labels": []},
  "scheme": {},
  "records": [],
  "active_annotation_ids": [],
  "deactivated_annotation_ids": [],
  "record_layers": {},
  "frame_state_records": [],
  "active_frame_state_records": {},
  "created_at": "ISO-8601 timestamp",
  "updated_at": "ISO-8601 timestamp",
  "history": []
}
```

Older v1 documents without State/Scheme fields load with empty histories. State
pointers serialize frame indices as string keys, e.g. `{"966": "state-record-id"}`.
State history is independent of Object records/layers. An active empty-state
judgment differs from no active State record.

Load validates geometry, frame bounds, active IDs, duplicates, lineage and cycles.
Portable identity includes filename/size/count/dimensions, not the absolute Cine
path or raw pixels. It is not a full-file cryptographic identity check.

## Derived edits, Undo and provenance

Manual A → edited B appends B with `derived_from=A`, deactivates A and activates B.
Model A → human B preserves model ID/confidence/geometry in A and creates manual
B in Reviewed. Ground Truth derivation exists as a backend operation; it is not
an automatic approval workflow.

QUndoStack/QUndoCommand handles add/edit/deactivate/State operations. Redo appends
a record only once; later Undo/Redo changes active pointers, retaining history.
Temporary polygon draft history stays outside the document until Confirm. A
multi-component Wand confirmation is one undo macro.

Object attributes can retain raw TIME64, relative timestamp, display review
context, optional `instance_name`, and Wand seed/settings. FrameStateRecord stores
TIME64 directly, immutable State IDs, separate `quality.uncertain`, notes and
`derived_from`. Notes expansion is UI-only; there is no `has_note` scientific field.
Display gain, colors and badges never become geometry or scientific intensity.

## Persistence and dirty state

Formal save writes a same-directory temporary file, flushes/fsyncs, then atomically
replaces the destination. Failed replacement preserves the original file.
Autosave uses a separate recovery path and does not reset formal dirty state.
Dirty tracking follows document revisions/audit changes, not only visible geometry
or the Undo stack's clean index. ViewerSession has separate persistence semantics.

## Scheme and display resolution

Scheme owns runtime Object/State display metadata and links to versioned definitions.
The approved Scheme retains semantic IDs and rules. Custom UI copies alter names
and enabled flags without ID migration. Arbitrary Object labels are supported by
the record/taxonomy interfaces; they do not redefine the approved six-label baseline.

Object order/style, daughter palette and common/more State grouping are resolved
from Scheme display configuration. Invalid display metadata reports a warning and
uses safe defaults. Normal viewing can apply current display revisions without
rewriting saved geometry; package mode uses its embedded display snapshot.
Positive instance-name suffixes give stable daughter ordinals/colors; unnamed
objects use deterministic ordering. Layout and tool behavior remain UI concerns.

## Review and prediction boundaries

Portable Review Package keeps an immutable exported base plus a derived review
document. Import compares base IDs/ancestry against local active records. Returned
Object changes enter Reviewed; Manual stays active and unchanged. State candidates
are appended to history without replacing canonical active State pointers; import
audit metadata identifies candidates and decisions. No automatic Ground Truth or
Queue completion occurs. See [review conflicts](portable_review_package.md#returning-to-annotator).

PredictionProvider/layer interfaces are extension points. Full Prediction Store,
model execution/import, dataset export and Measurement Store remain planned; do
not treat record support or synthetic tests as deployed AI capability.

## Timeline contract

Human marker membership derives from active human Object roles and active human
or reviewed/ground-truth State records; prediction-only frames are excluded.
The slider aggregates by native groove pixel column. Hover details are resolved
lazily from the current document/Scheme/language. Marker clicks emit the existing
navigation request and cancel stale debounce, while normal drag/key events retain
native behavior. Markers persist only indirectly through annotation records.

Related: [Data Architecture](data_architecture_concept_v1.md) · [Editor](annotation_editor.md) · [Index](README.md).
