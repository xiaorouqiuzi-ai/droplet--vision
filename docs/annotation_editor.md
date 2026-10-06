# Annotation Editor

Implemented workflow for Object annotation and Frame State. Scientific label
meanings are defined only in the [labeling scheme](annotation_labeling_scheme_v1.md);
data organization is defined in [Data Architecture](data_architecture_concept_v1.md).
For installation use [Getting Started](getting_started.md).

## 10-minute first annotation walkthrough

1. Open a Cine and wait for a frame. Keep Auto Fit on initially; use Raw/Ref90
   comparison to inspect visible structure without changing coordinates.
2. In the left **Annotation Scheme** group select the approved scheme and **Apply**.
3. On the right choose the unlocked **Manual** drawing layer.
4. Choose **Parent droplet / 父液滴**. The first compatible tool is Polygon;
   later selections may recall the label's last compatible tool.
5. Click several boundary vertices. Click the first vertex, double-click or
   press Enter to close. **Dashed means draft**, even after closing.
6. Drag solid vertex handles; click/drag a hollow midpoint to insert a vertex.
7. **Confirm / Enter** creates a solid record. Esc before confirmation discards
   the draft. Point annotations instead commit on a single click.
8. Inspect nearby frames before selecting a temporal Frame State. Use More States
   for multiple additional states. Add Uncertain/Notes where appropriate.
9. Save with **Ctrl+Shift+S**. Verify the file path on the left. Click the upper
   timeline triangle to revisit this frame.
10. Reopen the same Cine and load that JSON with **Ctrl+Shift+O**. Check geometry,
    states and notes. Saving ViewerSession with Ctrl+S is a separate operation.

## Workspace and Annotation Scheme

The left scrollable dock holds data/timing/display information, Scheme controls,
current document location and the current-frame annotation list. The right side
holds Drawing Layer, Object buttons, the one-row Select/Polygon/Wand/Point tools,
dynamic settings, Frame State, and quality/notes. Queue remains independent.
Long metadata values wrap and can be selected/copied.

Scheme selection requires **Apply**. Apply cancels temporary drawing but retains
records. **Modify…** edits a custom copy's display names/enabled flags, with stable
IDs read-only. Save as a new JSON, then Apply; approved configs cannot be overwritten
through this UI. **Open Scheme…** loads a custom JSON. A document retains its active
Scheme snapshot. Unknown/legacy object IDs remain identifiable.

The runtime Scheme controls object order/names/enabled flags, allowed geometry,
colors and State display/order/common grouping. Layout remains application code.
Semantic IDs/meanings require scheme versioning; display metadata may evolve
separately. See [developer contracts](annotation_architecture.md).

## Drawing Layer and Object selection

Drawing targets an unlocked **Manual** or **Reviewed** layer. Visibility and
locking are distinct controls. Prediction and Ground Truth start locked; they
are not direct drawing targets. Existing model edits create Reviewed derivatives
and retain the original prediction, when explicit layer policy permits editing.
There is no integrated model inference workflow.

Object buttons are Scheme-driven and exclusive. The approved display order is
parent, cavity candidate, daughter, flame, support, soot. An incompatible tool
is replaced with a compatible one; enabled geometry restrictions still apply.
BBox remains loadable/editable but is hidden from primary creation tools.

## Polygon drafts and persisted editing

```text
Open Draft → Close Draft → Edit Closed Draft → Confirm → Persisted
```

Click to append vertices; move the pointer to preview the next segment. Backspace
removes the last vertex. At least three vertices are required to close/confirm;
the first point is not duplicated in saved geometry.

Solid square handles are real vertices; smaller hollow squares are edge midpoints,
including the closing edge. Drag a vertex to move it. Click/drag a midpoint to
insert and optionally move a vertex. On a selected persisted polygon, double-click
an edge inserts the nearest projected point on that edge. Delete or right-click
Delete Vertex removes a selected real vertex only if at least three remain.
With no selected vertex, Delete deactivates the selected annotation.

Draft edits have transient Undo/Redo. Confirmation is one document command;
a persisted vertex/midpoint edit produces one derived record on release. Original
records are retained. Esc cancels temporary changes. Switching frame/tool/label
can cancel an unfinished draft; Confirm before navigating if you want to retain it.
Whole-object dragging and mask brushing are not offered as completed features.

## Magic Wand assisted annotation

Magic Wand is a **grayscale selection aid, not an automatic physical classifier**.
It reads the current **raw uint8 grayscale** array even in Ref90 display. Choose
a label, click a seed, then adjust Tolerance (0–50) and Connectivity (4/8).
Default tolerance is 10 and connectivity 8, from the
[Wand preset](../configs/annotations/magic_wand_v1.json), not scientific thresholds.
The seed reference is the clamped 3×3 median.

Replace selects a new region; Add unions another region; Subtract removes one.
Selections above the configured area fraction are refused with a warning.
Contours are simplified into editable closed polygon drafts; manually adjust
vertices, then Confirm. Disconnected components create separate polygons in one
Undo macro. Holes/degenerate contours are refused rather than silently filled.

Changing tolerance/connectivity or seeding again can regenerate contours. After
manual boundary edits a confirmation protects those adjustments; Cancel restores
the prior settings/geometry. Creation provenance records seed/settings and manual
adjustment, but no mask is serialized. Result source is manual, not model.

## Point, selection and instance naming

Point places one raw-coordinate point on click, when allowed by the label.
Select a canvas shape or left-side list item; selection stays synchronized and
shows record ID, label, source, review status and lineage. Drag a point to edit.
Existing BBox corners can be resized. Geometry clamps to image bounds.

`instance_name` is optional. **Auto name** proposes an unused current-frame name;
**Apply name** (or Enter in the field) creates an undoable derivative. It is neither
a model class nor a tracking ID. `annotation_id` remains the unique record ID.

## Scheme colors and daughter numbers

Colors come from Scheme display metadata. The current palette uses blue
`#3B6FB6`, teal `#2A9D8F`, orange `#E9A23B`, purple `#7A6FAC`, coral `#D96C75`
and blue-grey `#7B8794`. Parent is blue, cavity candidate purple, flame orange,
support blue-grey and soot coral. The Scheme remains the authoritative color source.

Daughters cycle the configured palette. A positive numeric instance-name suffix
such as `Daughter_03` selects number 3 and the corresponding cycle slot; unnamed
objects use deterministic current-frame ordering. Canvas circle/number badges
and list swatches use the same resolver. Save/load and derived edits preserve
named-instance mapping. Color/number never enters Ground Truth geometry.

## Frame State and quality

State applies to a whole frame and has no geometry. The approved Scheme exposes
four common checkboxes: Simple evaporation, Micro-explosion, Burning and Secondary
breakup. **More States** contains six checkable menu actions and shows a selected
count. Multiple selections are allowed; Chinese names include the English term,
for example **喷发（Puffing）**.

The current entry rule makes Simple evaporation exclusive with all other states.
It is a workflow constraint, not a new physical definition. Each committed change
creates an immutable FrameStateRecord and one Undo command; TIME64 comes from
the current frame. An active empty-state record differs from never inspecting a frame.

Uncertain is an independent quality flag. Notes are hidden unless Uncertain,
Have note, or nonempty saved notes requires them. Have note is UI expansion state,
not a persisted scientific field. Unchecking it never silently erases text: choose
keep, clear or cancel. **Apply notes** commits; pending notes also flush before
navigation, saving and dirty checks. Notes are optional even with Uncertain.

## Timeline markers

An upper triangle/short tick means an active human Object or human-reviewed
Frame State exists there; pure predictions do not create it. Click within the
15-pixel-wide screen-space hit area to navigate; hover for frame, object count
and State names. Multiple frames in the same screen column share a marker;
click chooses the one nearest the current frame, with earlier index breaking ties.
Tooltip identifies this aggregation. Native slider dragging and keyboard behavior
remain unchanged outside the upper marker hit area.

Markers update on editing, deactivation, Undo/Redo and loading. Package available
and target markers remain distinct lower markers. Alt+Left/Right also navigate
annotated frames; a marker is not a Queue Done flag or Ground Truth approval.

## Saving, history and recovery

**Save Annotations** writes an AnnotationDocument atomically (temporary file,
fsync, replace). Default standalone location: `outputs/annotations/`; queue-managed
work uses the queue's `annotations/` directory. Current Annotation Data shows actual
or suggested paths plus dirty status, Copy Path and Open Folder.

Edits append records with `derived_from`; Delete deactivates rather than erases.
Undo/Redo changes the active view but preserves history. Consequently returning
to an earlier visible shape may still leave unsaved audit/history changes.
Changing Cine, loading another document or exiting protects dirty work with
Save/Discard/Cancel. Autosave runs every 30 seconds when dirty, under an ignored
autosave directory, and does not mark the formal document saved.

Open Annotations checks Cine identity/dimensions and validates geometry/history.
ViewerSession does not contain annotations. In package mode annotation Save routes
to **Save Reviewed Package As…**; see [review instructions](portable_review_package.md).

## Language and branding

中文/English switches live from the top button or Settings, preserving Cine,
frame, draft, selection and unsaved records. Stable IDs/storage keys do not change.
Scheme-localized names are resolved on switching. Help → About shows version,
repository owner `xiaorouqiuzi-ai`, repository link and the icon derived from
project `planico.jpg`.

## Keyboard shortcuts

| Key | Action |
| --- | --- |
| 1 / 2 / 4 / 5 | Select / Point / Polygon / Magic Wand |
| Enter | Close open draft; Confirm closed draft |
| Esc / Backspace | Cancel temporary work / remove last open polygon vertex |
| Delete | Delete selected vertex, otherwise deactivate selected annotation |
| Ctrl+Z / Ctrl+Y or Ctrl+Shift+Z | Undo / Redo; draft history first when active |
| Alt+Left / Alt+Right | Previous / next annotated frame |
| Ctrl+Shift+S | Save Annotations |
| Ctrl+Shift+O or Ctrl+Alt+O | Open Annotations |
| Ctrl+S | Save ViewerSession separately |
| R / P / E | Raw / Ref90 / previous enhanced display |

Related: [Viewer](cine_viewer.md) · [Label definitions](annotation_labeling_scheme_v1.md) · [Index](README.md).
