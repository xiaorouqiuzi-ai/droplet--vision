# Annotation Package — 标注包

Implemented offline collaboration through a single `.dvapkg` file, without sharing
original Cine datasets. Annotation Package is transport for raw-frame subsets and
human annotation snapshots, **not a fourth canonical data layer**. Original
AnnotationDocument remains the human source; returning reviews are candidates.


## Creating an Annotation Package from a Cine

**Functions → Create Annotation Package from Uniform Cine Sampling…** works with a
single selected Cine, even with no open AnnotationDocument or existing annotations.
Choose the Cine, requested sample count (default 50, range 2–10000), purpose
(annotation/review/general), and optional context radius (default 0). The dialog
reads metadata in a worker and previews actual count, first/last and approximate interval.

For F = 32196 and N = 50, export produces **exactly 50 target frames**, including
frame 0, frame 32195 and 48 uniformly distributed intermediate frames:
**50 sample points = 49 intervals**, approximately 657.04 frames apart.
`uniform_frame_indices(F, N)` rounds `i * (F - 1) / (N - 1)` to the nearest integer
(ties to even), with deterministic bounds/correction and an explicit uniqueness check.
When F < N, the UI requires confirmation to export all F unique frames; Cancel exports
nothing. A one-frame Cine produces one target after this confirmation.

Every sampled point is a target. Optional context is extra, clamped and deduplicated;
it never changes the target count. This uses frame index, **not header FPS, TIME64
spacing, image-change scores or physical-event classification**. The existing
`frame_sampling_v1` anchor/change-peak Queue sampler is unchanged.

Default filename: `<cine_stem>_uniform_<N>.dvapkg`. Default output is under
`outputs/annotation_packages/exported/`. Never export inside the source Cine directory.
Frames are read lazily, encoded and pixel-checked one at a time; the container retains
compressed PNG bytes, not a decoded full video. Package safety size limits still apply.

## Annotation Package v2 and legacy compatibility

New exports use `package_kind = "annotation_package"`, `package_format_version = 2`
and `package_purpose = "annotation"`, `"review"` or `"general"`. Purpose describes the
workflow and does not restrict the editor. The annotation document schema stays unchanged.
**Zero object records and zero Frame States are legal** when raw frames are present.
The immutable base snapshot can be empty. Uniform export includes annotations from the
currently open matching Cine document if available; otherwise it creates an empty base.

Older `.dvrpkg` files remain supported, including v1 manifests with no `package_kind`.
Open accepts `.dvapkg` and `.dvrpkg` without manual migration, and preserves old review
metadata. Save As defaults to a new `_annotated.dvapkg` name; saving a legacy package
retains its validated legacy manifest. SHA-256 inventories are regenerated on every save.

Functions contains independent utilities and collaboration workflows; ordinary Cine,
AnnotationDocument and Session operations keep their existing menus. Future extraction,
dataset export, prediction import and measurement export are not implemented here.

## Annotating from zero

Open the raw-only package from **Functions → Open Annotation Package…**. No CineReader
or original dataset is needed. Use Polygon, Magic Wand, Point, labels, Frame States,
Notes, Uncertain and Rename. Save As, close and reopen to continue annotation.

The full-index timeline remains 0…F−1. Click lower available/target markers or use
Previous/Next available frame. Unpackaged frames produce a message and retain the
actual displayed frame and TIME64. The left panel reports target/done/remaining counts.
A target counts as done for this progress display if it has an active human object,
active human Frame State or an explicit “Mark frame reviewed” action. Merely viewing
it never completes it. These PENDING/DONE progress semantics are not scientific approval
or Queue status, and individual records remain unreviewed until explicitly reviewed.

Return the saved package to its sender. For a flagged empty base, a matching Cine's
new AnnotationDocument may receive new objects as Reviewed/manual candidates even if
its document UUID differs. Cine identity, file size and dimensions still must match.
For nonempty bases the original document ID and immutable base records are still required.
Returned Frame States remain history candidates, as explained below.

## For Annotator

1. Open the Cine and its AnnotationDocument. **Save Annotations** first, retaining
   that original document ID/history for the eventual merge.
2. Choose **Functions → Create Annotation Package from Current Annotations… / 从当前标注创建标注包…**.
3. Select current frame, all human-annotated frames in this Cine, or selected Queue
   statuses (defaults DONE/NEEDS_REVIEW). Queue export requires its local dataset
   root and associated saved documents; same-Cine current unsaved edits are included.
4. Set context before/after each target: default **±5**, allowed 0–100. Context
   clamps to Cine bounds and deduplicates overlapping frames. It is not a review target.
5. Optionally enter a creator alias. Save a new `.dvapkg`; default directory is
   `outputs/annotation_packages/exported/`. Export summary reports actual frames,
   objects/states and bytes. No fixed compression ratio is promised.
6. Send that file to the reviewer using your chosen transfer method. The application
   does not upload it or synchronize a server. Retain your original document and Cine.

Optional unpacked-folder export creates a new directory with the same contents;
Functions → Open Annotation Package Folder… reads it. Prefer the single file when sending,
so no PNG or checksum member is accidentally omitted. Different Scheme snapshots
must be exported separately. A custom frame checklist is not implemented.

## For Reviewer

1. Follow [Getting Started](getting_started.md) to install/launch the source checkout.
   You need the package, **not the original Cine or its folder structure**.
2. Choose **Functions → Open Annotation Package… / 打开标注包…** and enter an optional
   reviewer alias. No legal name is required. Integrity errors stop loading.
3. Confirm the title says **Annotation Package Mode / 标注包模式**. The left panel
   names the package, original Cine total and available packaged-frame count.
4. Use **Previous/Next review target** for assigned frames and **Previous/Next
   available frame** for context. Multi-Cine packages have a Cine selector.
5. Inspect Raw/Ref90, objects, State and notes. Use the existing Select/Polygon/
   Wand/Point tools to edit or add. Accept/Reject selected objects creates decisions;
   deletion in this mode records rejection rather than removing the original snapshot.
6. Edit State checkboxes/quality/notes or use Accept/Reject/Needs Review for the
   active State. Add an optional **Review note…** for the frame. Mark frame reviewed
   explicitly; opening a frame alone does not count as progress.
7. If finished, choose **Complete review** explicitly. Otherwise status remains
   `in_review`. Further edits invalidate completion. Undo/Redo retains original history.
8. **Functions → Save Annotation Package As… / 保存标注包为…** writes a new
   `_annotated.dvapkg`. Annotation Save also routes here in package mode. Return
   this new file; retain the received original.

Switching package Cine retains each document's in-memory changes but clears the
current Undo stack. Closing/switching away checks dirty work across the whole
package. Autosave under `outputs/annotation_packages/temp/` is a recovery copy, not
formal Save. Package path/dirty state are visible in Current Annotation Data.

## Returning to Annotator

1. For packages with existing base records, open the **original Cine and original
   AnnotationDocument**. For an empty-base task, open the matching Cine; a newly
   created document is allowed. Save any local work before importing as usual.
2. Choose **Functions → Import Returned Annotation Package… / 导入返回的标注包…** and select the returned `.dvapkg`.
3. If local active A is unchanged, reviewer A → B imports as Reviewed B. Manual A
   remains active and its original content is unchanged. New reviewer objects also
   enter Reviewed; rejected derivatives remain history without deleting local Manual.
4. If you changed A → C while the reviewer made A → B, the conflict dialog shows
   Base / Local / Reviewer. Explicitly choose **Keep local**, **Use reviewer as
   Reviewed candidate**, **Keep both as Reviewed candidates**, or **Defer**.
   There is no default choice and no silent overwrite.
5. Inspect the Reviewed layer and lineage, then **Save Annotations** to persist
   the merge. Original Manual remains available for comparison. Reimporting the
   same returned record does not duplicate it; ID collisions with different content fail.
6. Evaluate final acceptance separately. No returned change automatically becomes
   Ground Truth and no Queue item is automatically marked Done.

Returned Frame State candidates are retained in immutable State history and import
metadata, without replacing the local active State pointer. **A dedicated State
comparison/adoption UI is not implemented**; inspect JSON/history when evaluating
those candidates. Keep-both preserves the local State and returned candidate.
There is no automatic bulk promotion to Ground Truth.

## Available frames and timing

A package is sparse, not a complete Cine. Unavailable navigation shows a message
and retains the current image, never inventing a black frame. The full-index
slider has lighter lower ticks for available frames and orange lower triangles
for targets. Upper human annotation markers remain separate and clickable.
Playback follows available frames and is not evidence of continuous experimental time.

Raw TIME64 integers, relative timestamps and timing status are copied directly.
The reviewer must not reconstruct timing from frame index/header FPS. Preserve
unresolved mismatch even when the image looks correct.

## Raw pixels, Ref90 and Scheme snapshot

v2 exports **raw uint8 grayscale PNG**, checks pixel equality on writing and saves
SHA-256. No screenshots, enhanced previews, full Cine, absolute dataset root or
raw pixels inside annotation JSON are included. Geometry stays in raw image space.

Ref90 preset ID, reference frame/P90, target and locked gain are display provenance.
The reviewer applies the same gain to raw PNGs without reading Cine or re-estimating
per frame. Missing valid gain gives Raw fallback. Scientific grayscale remains raw.
Manual/Auto are separate display modes; Wand still consumes raw pixels.

The embedded Scheme includes Object taxonomy, State schema and display settings.
Package mode uses that snapshot rather than local palette revisions. Unsupported
semantic configurations fail explicitly, never relabeling silently. Stable IDs,
reviewer alias, package ID, application versions and `derived_from` preserve provenance.
Original snapshots are immutable; reviewer records are manual, not model predictions.

## Container and integrity

```text
manifest.json
scheme/annotation_scheme.json
scheme/object_taxonomy.json
scheme/frame_state_schema.json
frames/<logical-cine-id>/frame_000966.png
annotations/<logical-cine-id>.review_annotations.json
review/review_state.json
checksums/sha256.json
```

Manifest records format/package/app versions, creator, Cine identity, frame roles,
TIME64, PNG hashes, base document ID/full hash/snapshot hash/active IDs and gain.
Annotation containers hold immutable base and review documents for exported frames
plus required ancestry. No complete Prediction Store is included; necessary model
ancestors of human-reviewed records retain their provenance.

Checksums cover every payload member and detect corruption, not authentic reviewer
identity. Structural validation rejects unsafe/absolute paths, traversal, symlinks,
duplicates, unsupported images, altered base records and unexpected files. JSON
with accidental local absolute paths is rejected rather than silently disclosed.
ZIP contents are read in memory without extraction into dataset folders. Expanded
ZIP budget is 1 GiB, single member 128 MiB, at most 20,000 members: use small batches.

Saving stages a temporary container beside the destination, flushes/fsyncs and
validates it, then uses atomic replace. Failure preserves the existing destination.
Source Cine size/mtime are checked unchanged after export. Checks are not proof
against malicious edits that preserve file metadata.

## Scope and troubleshooting

| Situation | Action |
| --- | --- |
| Corrupt/missing checksum or PNG | Obtain an intact copy; do not bypass validation |
| Document ID/base mismatch on import | Locate the actual original annotation document |
| Unknown Scheme semantics | Use compatible software/configuration; do not rename labels |
| Queue item has no document link | Save/associate that Cine's annotations before export |
| Unsupported color/uint16 input | Package export supports uint8 grayscale only |
| Reviewer needs unbundled context | Annotator exports a new package with sufficient context |

Per-frame review notes are supported; a per-annotation note UI is not. No cloud
sync, database, real-time coediting, scientific measurement or full-Cine tracking
is performed in review mode.

Related: [Editor](annotation_editor.md) · [Data Architecture](data_architecture_concept_v1.md) · [Index](README.md).
