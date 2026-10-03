# Annotation Editor v1

Implemented in the current working tree for review; not yet committed or pushed.
Launch with `launch_viewer.cmd` or `python scripts/launch_viewer.py` in VisionLab.
No new dependencies are required. Raw Cine input remains read-only.

## Drawing and editing

Open a Cine, select an enabled taxonomy label, and choose an unlocked Manual or
Reviewed layer. The toolbar says **Drawing into: ...**. Geometry availability is
read from the label's `allowed_geometry_types`; label IDs are open strings.

| Shortcut | Action |
| --- | --- |
| 1 / 2 / 3 / 4 | Select / Point / BBox / Polygon |
| Esc | Cancel temporary drawing or edit |
| Enter or double-click | Commit polygon (at least three distinct vertices) |
| Backspace | Remove last polygon vertex |
| Delete | Deactivate selected annotation, retaining history |
| Ctrl+Z | Undo |
| Ctrl+Y or Ctrl+Shift+Z | Redo |
| Alt+Left / Alt+Right | Previous / next frame with active annotations |
| Ctrl+Shift+S / Ctrl+Shift+O | Save / open annotation document |
| Ctrl+Alt+O | Alternate open shortcut if the desktop intercepts Ctrl+Shift+O |
| Ctrl+S | Save ViewerSession, independently of annotations |

Point is a single click. BBox is press, drag in any direction, release; drawing
requires at least one raw pixel of width and height, a UI geometry rule rather
than a physical resolution criterion. Polygon is a series of clicks with a
moving preview segment; its first vertex is not duplicated when closed.

Select a shape on the canvas or in the current-frame list. Selection highlights
the shape and shows label, geometry, record ID, source, review status, model
ID/confidence and parent record ID. Drag polygon vertices, any bbox corner or
a point. Dragging changes a temporary working geometry; release commits one
derived record and one undo command. Locked or hidden layers cannot be edited
or deactivated. To edit a model record, explicitly unlock its layer; the result
goes to an unlocked Reviewed layer and leaves the original prediction intact.

Switching frames cancels unfinished drawing/editing. Editing is disabled while
the next frame loads, avoiding accidental annotation of the previous frame.
Committed records remain in the document. The toolbar shows current-frame
annotation count and the total number of annotated frames.

## Coordinates and provenance

Coordinates always refer to **raw image pixel centers**: top-left origin,
x = column, y = row, with bounds `[0, width-1]` and `[0, height-1]`. Subpixel
coordinates are supported. Drawing clamps to these bounds; loading validates
finite coordinates and bounds without silently changing the geometry.

Raw/Ref90/Manual/Auto, zoom and pan never modify saved coordinates. Photometric
gain is not stored in geometry. New records include `attributes.raw_time64`,
`attributes.relative_timestamp_s`, and optional `display_mode_used`. These come
from the current FrameResult/display state; no nominal-FPS time fallback exists.
The editor records the selected label without inferring physical phase or events.

## Documents, history and undo

AnnotationDocument is independent from ViewerSession. It contains Cine identity,
image dimensions, taxonomy metadata/snapshot, an append-only AnnotationStore,
active and inactive IDs, record-to-layer membership and an event history.

Adding creates a manual/unreviewed record. Editing creates a new manual/edited
record with `derived_from`; model metadata remains on the original prediction.
Deleting only deactivates the ID. QUndoStack commands restore active views;
they never erase historical records. Undo to a previously saved active view
can still leave the document dirty because its audit history has grown.
The undo stack itself is not restored after loading; the complete records and
active view are restored. Backend `derive(..., review_status="ground_truth")`
supports a retained-history Ground Truth derivative; approval UI is deferred.

## Saving, recovery and dirty protection

Annotation menu offers New, Open, Save and Save As. Default formal output is
`outputs/annotations/<cine_stem>.annotations.json`. First save asks for a path;
later Save uses that path. Files are Git-ignored and are never written back to
the Cine directory by default. Only `.json` destinations are accepted.

Saving creates a uniquely named temporary file in the destination directory,
flushes and fsyncs it, closes it, then uses `os.replace`. A failed save preserves
the previous formal JSON and leaves the document dirty. This protects against
partial JSON replacement; it is not a guarantee against every storage failure.

An asterisk marks unsaved annotation changes. New/open document, changing Cine,
Close Cine and app close offer **Save / Discard / Cancel**. Cancel or a failed/
cancelled Save leaves the current document in place. Cine matching checks
filename, size, frame count, dimensions and Cine ID; a mismatch is rejected.
These checks do not constitute a cryptographic identity guarantee.

Every 30 seconds, dirty documents are atomically autosaved to
`outputs/annotations/autosave/<cine_stem>.<document_id>.annotations.autosave.json`.
The UUID prevents same-stem recovery collisions. Autosave does not clear dirty
state, change the formal save path or replace an explicit Save. Recovery files
are retained after formal Save and can be opened through Open Annotations.
ViewerSession continues to contain only UI state/bookmarks/notes.

## Limits

Only point, bbox and polygon documents are editable/validated in v1; other
geometry schemas remain future extensions and unsupported documents fail closed.
No whole-object polygon/bbox translation, vertex insertion/deletion after commit,
mask brush, database, dataset export, YOLO/Torch, inference, tracking or scientific
measurement is included. There are count indicators instead of timeline ticks.
History is in-memory until save/autosave; large-history indexing is future work.
