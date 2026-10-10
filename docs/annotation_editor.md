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
7. **Space / Enter / Confirm** creates a solid record. Esc before confirmation discards
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

Space uses the same Confirm command as the button, including one compound undo for
multiple Magic Wand components. Esc cancels the active draft. Text inputs keep
normal spaces; focused buttons keep their native action, without a second canvas action.

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

See also the Cine-local reuse workflow below.

| Key | Action |
| --- | --- |
| 1 / 2 / 4 / 5 | Select / Point / Polygon / Magic Wand |
| Space (canvas focus) | Confirm closed polygon / Magic Wand draft; open draft: hint only, no playback; no draft: Play/Pause |
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

## Cine-level droplet support rod template

The UI calls `support_structure` **载滴杆 / Droplet support rod**; the stable ID,
semantic definition and Scheme color are unchanged. Static projection is an
annotation convenience, not a scientific assertion of perfect immobility.

1. Select the rod label and confirm one or more Polygon/Magic Wand annotations
   on an unlocked Manual/Reviewed layer. Drafts and model-only records are not
   eligible template sources.
2. Check **应用全 Cine / Apply to entire Cine**. On first use this captures all
   eligible current-frame rod polygons. An existing template is reused. The
   controls show its source frame and count, and are completely hidden for
   other object labels. Without a template or confirmed polygons the checkbox
   is disabled.
3. Navigate anywhere in this Cine: the Viewer projects the same immutable raw
   geometry (plus any manually saved frame offset). It creates **no per-frame records**. The source annotations remain
   ordinary active records, without duplicate overlays on their source frame.
4. Uncheck to turn projection off. Template references, source records and any
   local overrides remain intact. **Update Cine Support Rod Template** is the
   explicit way to replace the source set; ordinary editing never updates it.
5. Select a projected polygon and edit/rename it normally. The first committed
   edit creates a manual **Frame override** on this frame; subsequent edits use
   derived-record history. Its provenance contains
   `creation_tool = cine_support_template_override`,
   `template_source_annotation_id`, `template_source_frame_index`, and the
   current frame's TIME64/relative timestamp. Cross-frame copies do not pretend
   to be same-frame revisions: the first override has `derived_from = null`.
6. Save the AnnotationDocument. The template, enabled state and overrides survive
   reload and same-Cine queue navigation. Another Cine uses its own document.

Set/update, enabling/disabling, local edits and deletion support Undo/Redo.
Existing legacy per-frame template copies remain valid and take precedence over
projection for their source rod. No migration or mass duplication is performed.

The optional, backward-compatible metadata is:

```json
{
  "cine_templates": {
    "support_structure": {
      "apply_entire_cine": true,
      "source_frame_index": 966,
      "annotation_ids": ["confirmed-record-id-1", "confirmed-record-id-2"]
    }
  }
}
```

Missing `cine_templates` means no template. Missing `apply_entire_cine` means
projection is off. References point to retained immutable records; an edited
or deactivated source does not silently replace the stored template geometry.

### Sparse support-rod alignment

Use the clearest frame (often the last frame) to confirm one or more rods and
**Apply to entire Cine**. On another frame select the rod label/annotation and
activate **Select**. One four-way **✥** move handle appears at the combined
bounding-box center of the entire template set, distinct from square vertex
and midpoint handles. Its screen-space arrow spans about 16 px, with a 20 px
hit area; zoom/pan do not change the raw-coordinate offset.

Drag the handle to translate all rods together. Mouse movement only previews;
release commits **one Undo command**. Shape, vertex order and relative positions
are preserved. The whole shared delta is clamped at image bounds rather than
clipping individual vertices. Esc or frame/tool changes cancel an unfinished
drag. The handle is shown only in Select mode for a selected rod label/record,
with the entire group visible and editable; hiding/locking part of the group
suppresses it, so hidden rods are not moved unexpectedly.

Tool Settings shows the absolute **Frame offset** relative to the template.
**Reset frame position** (also on the handle context menu) removes that frame's
sparse offset; Undo restores it. Missing offsets mean `(0, 0)`. Returning to zero
does not leave an explicit zero entry. The source frame may also have a local
offset, with a warning that the template itself remains unchanged.

```json
{
  "frame_overrides": {
    "15460": {"translation": {"dx": -2.4, "dy": 1.7}}
  }
}
```

This optional node lives inside `cine_templates.support_structure`. Only edited
frames are stored; old documents without it load normally. Values must be finite
raw-pixel deltas and the projected group must stay within image bounds. No raw
pixels, scientific timing, interpolation, tracking or physical-motion measurement
are calculated or changed. Save/reload preserves these exact offsets.

Rendering precedence is **full frame-local geometry > frame translation > global
template**, while unrelated ordinary annotations remain independent. Editing a
vertex/midpoint of a translated projection materializes the **entire currently
projected group** into frame-local full geometry, incorporates the offset once,
and clears the sparse translation in the same Undo action. Subsequent whole-group
moves derive new local records without updating the template. Full geometry is
shown as **Frame override**; Reset is disabled in that mode because an arbitrary
shape edit has no single reversible offset. Use Undo or delete the local overrides.
Deleting each materialized override falls back to its original zero-offset global
polygon; undoing materialization restores the sparse translation instead.

Existing legacy partial full overrides take precedence for their corresponding
rod. A group move with any full overrides materializes/derives the whole displayed
group, preserving its relative layout. Explicit template replacement starts a new
reference set without carrying offsets from the previous template. Updating from
a translated projection requires first confirming it as full local geometry;
hidden source records are never inadvertently added to that new set.

A saved translation is human work: its frame gets a timeline marker and participates
in annotated-frame navigation, even with the eye off. Pure global projection still
does not mark every frame. Projected list rows include their offset; full overrides
remain distinctly labelled.

### Current annotation list actions

The list separates **Frame annotations** from **Templates**. Projected rows
are explicitly labelled *Cine template* or *Package template*, with the Scheme color and source name
(or a display ordinal). Select them to create an independent local correction.

Each row's small eye toggle hides/shows only that overlay. It does not change
selection, active IDs, geometry, review status or Ground Truth. Visibility is
stored in `ViewerSession.ui_state.hidden_annotation_ids`; save/open the Session
separately to restore it. A template's visibility key remains stable across
frames, so hiding one projected rod hides that rod throughout this session.
It does not disable **Apply to entire Cine**, nor hide a separate local override.

Right-click a real editable manual annotation and choose **Delete Annotation**
to deactivate it through Undo/Redo; its historical record remains. Prediction
and locked-layer deletion is disabled. In portable review mode, removal follows
the existing reject/review-derivative policy. A projected row instead offers
**Hide this template**, because it has no current-frame record to delete.
Deleting a local override restores its global projection when enabled.

Hidden real annotations still count for human timeline markers. Global template
projections do **not** add markers to every frame: only real source/override/
other human annotations, manual translation corrections and Frame States contribute. Counts also keep
frame records separate from transient projections.

### Portable review

Export materializes geometry only for the package's selected target/context
frames, without mutating the canonical document or forcing in the source frame.
These package-only records use the existing `source = imported` schema value
and `attributes.creation_tool = cine_template_projection`. They carry source
record/frame provenance, `frame_translation` dx/dy for translated snapshots,
and deterministic IDs; no new scientific source enum
is introduced. Materialized projections are not human-work timeline markers.

Reviewer edits become manual reviewed frame-local override candidates on import.
The original Cine template is never updated by review. Concurrent local overrides
a changed local offset, or a changed/disabled template require explicit conflict
resolution. Exported geometry already incorporates the frame translation exactly
once. A reviewer can move the materialized group using the same handle; its changes
return as Reviewed full-geometry local candidates, never as automatic template updates.
Package-local templates are separate from these legacy snapshots. Raw pixels,
TIME64 and Ref90 remain unchanged throughout this workflow.


### Cine scope versus package scope

**Apply to entire Cine ≠ Apply to entire package.** Normal Cine mode projects
`cine_templates` over the full Cine frame domain. Package Mode uses separate
`package_templates`, limited to the target **and context** frames physically
present in its manifest. Missing frames get no projection. Older packages without
this optional metadata have no package-wide template; retained Cine snapshot
metadata is not silently promoted into one.

Select **载滴杆 / Droplet support rod** to show the scope-specific checkbox.
Right-click a real editable rod row and choose **Set as support-rod template and
apply to entire Cine/package**. All confirmed editable support polygons on the
current frame form the set. Replacing an existing template requires **Replace
template / Cancel** confirmation. Explicit Update actions use the same confirmation.
Projection rows offer disable/hide rather than Delete; Reset frame position clears
a sparse translation.

Both scopes use the same projection resolver, center **✥** handle and Undo
commands. The combined rod bounding-box center moves the whole set; each frame
stores only its own dx/dy. Vertex editing after translation materializes that
frame's geometry overrides, leaving other frames and source geometry unchanged.
Package rows say **标注包模板 / Package template**, including offsets; geometry
corrections say **本帧覆盖 / Frame override**. Pure projections create no human
markers. Sources, translation corrections and full local overrides do.

Quick Save persists package templates and offsets. Undo to saved effective state
hides its save button. Returned templates become non-applied Reviewed candidates
in import history, including source geometry, available domain, offsets and
package provenance. They never replace the canonical Cine template. Dedicated
candidate adoption UI is deferred; this version retains candidates for explicit
review. See [package scope and schema](annotation_package.md#package-wide-support-rod-templates).
