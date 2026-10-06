# Portable Review Package — 便携审阅包

Implemented offline collaboration through a single `.dvrpkg` file, without sharing
original Cine datasets. Review Package is transport for raw-frame subsets and
human annotation snapshots, **not a fourth canonical data layer**. Original
AnnotationDocument remains the human source; returning reviews are candidates.

## For Annotator

1. Open the Cine and its AnnotationDocument. **Save Annotations** first, retaining
   that original document ID/history for the eventual merge.
2. Choose **File → Export Portable Review Package… / 导出便携审阅包…**.
3. Select current frame, all human-annotated frames in this Cine, or selected Queue
   statuses (defaults DONE/NEEDS_REVIEW). Queue export requires its local dataset
   root and associated saved documents; same-Cine current unsaved edits are included.
4. Set context before/after each target: default **±5**, allowed 0–100. Context
   clamps to Cine bounds and deduplicates overlapping frames. It is not a review target.
5. Optionally enter a creator alias. Save a new `.dvrpkg`; default directory is
   `outputs/review_packages/exported/`. Export summary reports actual frames,
   objects/states and bytes. No fixed compression ratio is promised.
6. Send that file to the reviewer using your chosen transfer method. The application
   does not upload it or synchronize a server. Retain your original document and Cine.

Optional unpacked-folder export creates a new directory with the same contents;
File → Open Review Package Folder… reads it. Prefer the single file when sending,
so no PNG or checksum member is accidentally omitted. Different Scheme snapshots
must be exported separately. A custom frame checklist is not implemented in v1.

## For Reviewer

1. Follow [Getting Started](getting_started.md) to install/launch the source checkout.
   You need the package, **not the original Cine or its folder structure**.
2. Choose **File → Open Review Package… / 打开便携审阅包…** and enter an optional
   reviewer alias. No legal name is required. Integrity errors stop loading.
3. Confirm the title says **Portable Review Mode / 便携审阅模式**. The left panel
   names the package, original Cine total and available packaged-frame count.
4. Use **Previous/Next review target** for assigned frames and **Previous/Next
   available frame** for context. Multi-Cine packages have a Cine selector.
5. Inspect Raw/Ref90, objects, State and notes. Use the existing Select/Polygon/
   Wand/Point tools to edit or add. Accept/Reject selected objects creates decisions;
   deletion in this mode records rejection rather than removing the original snapshot.
6. Edit State checkboxes/quality/notes or use Accept/Reject/Needs Review for the
   active State. Add an optional **Review note…** for the frame. Mark frame reviewed
   explicitly; annotation presence does not imply completion.
7. If finished, choose **Complete review** explicitly. Otherwise status remains
   `in_review`. Further edits invalidate completion. Undo/Redo retains original history.
8. **File → Save Reviewed Package As… / 保存审阅包为…** writes a new
   `_reviewed.dvrpkg`. Annotation Save also routes here in package mode. Return
   this new file; retain the received original.

Switching package Cine retains each document's in-memory changes but clears the
current Undo stack. Closing/switching away checks dirty work across the whole
package. Autosave under `outputs/review_packages/temp/` is a recovery copy, not
formal Save. Package path/dirty state are visible in Current Annotation Data.

## Returning to Annotator

1. Open the **original Cine and original AnnotationDocument**, not a newly created
   replacement document. Save any local work before importing as usual.
2. Choose **File → Import Review… / 导入审阅结果…** and select the returned `.dvrpkg`.
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

v1 exports **raw uint8 grayscale PNG**, checks pixel equality on writing and saves
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
| Unsupported color/uint16 input | v1 package export supports uint8 grayscale only |
| Reviewer needs unbundled context | Annotator exports a new package with sufficient context |

Per-frame review notes are supported; a per-annotation note UI is not. No cloud
sync, database, real-time coediting, scientific measurement or full-Cine tracking
is performed in review mode.

Related: [Editor](annotation_editor.md) · [Data Architecture](data_architecture_concept_v1.md) · [Index](README.md).
