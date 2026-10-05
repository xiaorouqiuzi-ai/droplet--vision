# Annotation Editor v1 / Annotation UX v1.1

正式标注类别、Frame State 和质量标记定义见 [Droplet Vision 标注内容方案 v1.0](annotation_labeling_scheme_v1.md)，该文件为标注内容规范的唯一依据。

Editor v1 and UX v1.1 are on main. Layout v1.2 is in the working tree for review.
Launch with `launch_viewer.cmd` or `python scripts/launch_viewer.py` in VisionLab.
No new dependencies are required. Raw Cine input remains read-only.

## Drawing and editing

Open a Cine, select an enabled taxonomy label, and choose an unlocked Manual or
Reviewed layer. The toolbar says **Drawing into: ...**. Geometry availability is
read from the label's `allowed_geometry_types`; label IDs are open strings.

| Shortcut | Action |
| --- | --- |
| 1 / 2 / 3 / 4 / 5 | Select / Point / BBox / Polygon / Magic Wand |
| Esc | Cancel temporary drawing or edit |
| Enter or double-click | Commit polygon (at least three distinct vertices) |
| Backspace | Remove last polygon vertex |
| Delete | Delete selected polygon vertex; otherwise deactivate selected annotation |
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
No whole-object polygon/bbox translation, mask brush, database, dataset export, YOLO/Torch, inference, tracking or scientific
measurement is included. There are count indicators instead of timeline ticks.
History is in-memory until save/autosave; large-history indexing is future work.

## Polygon vertex editing (UX v1.1)

In Select mode, double-click near an edge of the selected polygon. The new point
is the projection onto the nearest segment, inserted in boundary order (including
the closing segment). The pick tolerance is in screen pixels; the stored result
is in raw image coordinates, independent of zoom, pan and display mode.
Click a vertex handle to select it (orange); drag to move it. Delete removes the
selected vertex only if at least three vertices remain. Click the object/list to
return to annotation selection before deactivating the whole object. Insertion,
deletion and movement all create derived records and use the existing QUndoStack;
old geometry and predictions are never overwritten.

## 中文 / English

The default is `zh_CN`. Settings / 设置 → Language / 语言 → 中文 or English
persists a local QSettings preference. Restart to apply the language consistently;
the current document is not rebuilt or discarded. Central catalogs live under
`src/droplet_vision/ui/translations/`; missing keys fall back to English/source text.
Core menus, panels, actions and prompts are translated; diagnostic codes remain
stable. Taxonomy display names can be translated, but `label_id`, JSON statuses,
record IDs and arbitrary new taxonomy labels are unchanged. Unknown display names
remain as authored in the taxonomy. No scientific labels are inferred.

## Magic Wand assisted annotation

Choose an enabled label allowing polygon geometry and an unlocked Manual/Reviewed
layer, then press **5**. Click a seed, adjust Tolerance or Connectivity, and use
Replace/Add/Subtract for subsequent clicks. The translucent mask is temporary.
Confirm (or Enter) creates polygons; Cancel/Esc or frame changes discard preview.
No records are created before confirmation. Select mode can immediately correct
the resulting polygon vertices. Multiple polygons from one confirmation share
one compound Undo/Redo command.

**Magic Wand is a grayscale selection aid, not an automatic physical classifier.**
It reads the current cached **raw 2D uint8** array without mutation or further Cine
reads. Other dtypes/color input disable the tool; no scientific pixel conversion
is performed. Ref90/Raw/Manual/Auto affect only what is displayed.

Parameters have a single source: `configs/annotations/magic_wand_v1.json`.
Defaults are tolerance 10 (slider 0–50), 8-connectivity (4 also available), a
clamped 3×3 seed median, maximum region fraction 0.50 and RDP simplification
1.0 raw pixel. These are assistance settings, not scientific thresholds.
A pixel is eligible when its absolute difference from the seed median is at most
the tolerance. If noise makes the clicked pixel ineligible, the nearest eligible
pixel in the same 3×3 window starts the flood fill (ties by row, then column).
The noisy pixel is not silently added. Growing uses a bounded breadth-first walk;
excessively large regions or combined selections warn and cannot be confirmed.
Changing tolerance/connectivity recomputes only the latest operation against its
previous selection, so repeated adjustments do not accumulate duplicate regions.

Conversion traces ordered pixel-cell edges, separates diagonal contacts, maps
edges into the editor's raw pixel-center bounds and applies closed-ring RDP.
Simplification falls back if it produces fewer than three points or a crossing.
Disconnected components become separate records with the same chosen label.
**Holes are not supported by polygon v1:** confirmation warns and leaves the
selection uncommitted; adjust it rather than silently filling holes. Degenerate
regions that cannot form a valid polygon are also refused. The polygon is an
approximation of the selection; review and correct its vertices before ground truth.
Very complex contours can take longer on the GUI thread; no background classifier,
mask brush or automatic physical interpretation is included.

New records are `source=manual`, `review_status=unreviewed`. Attributes record
`creation_tool=magic_wand`, preset ID, tolerance, connectivity, seed reference,
all seed/operation settings, size limit and simplification tolerance, in addition
to existing TIME64/display provenance. No binary mask is serialized. Subsequent
edits retain these creation attributes and create a new `derived_from` record.
Raw arrays, FrameCache, Cine files, timing, scientific grayscale analysis and raw
PNG export remain independent of this assistance pipeline.

## Right-side workspace (layout v1.2)

Labels, tool buttons, current-tool settings, frame annotations and layers now share
the right dock. A first label selection recommends Polygon when allowed; returning
to a label restores its last compatible drawing tool. The status bar explains the
next gesture. Selecting a frame annotation switches to Select for editing. Tools
still obey taxonomy and layer restrictions, preserve immutable history and use raw
image coordinates. Display controls and all Cine/frame metadata are on the left;
Queue stays independent. See [layout and navigation](cine_viewer.md#workstation-layout-v12-working-tree-for-review).
