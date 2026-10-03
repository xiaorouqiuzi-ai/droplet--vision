# Frame Sampling + Annotation Queue v1

Implemented on main; no new dependencies or model
inference. The source dataset is read-only. Sampling produces candidates for
human annotation, not nucleation, puffing or micro-explosion classifications.

## Reproducible sampling

The single parameter source is
[`frame_sampling_v1.json`](../configs/sampling/frame_sampling_v1.json).
Queues retain its full resolved configuration, canonical JSON SHA-256, sampler
version and NumPy version. A change in parameters should use a new preset/output.

1. **Lifecycle anchors:** fractions 0.03, 0.10, 0.20, 0.30, 0.40, 0.50, 0.60,
   0.70, 0.80, 0.90, 0.97. Index = `round((frame_count - 1) * fraction)`, clamped
   and deduplicated. These are positions, not experimental times.
2. **Coarse probes:** at most 512 uniformly spaced, rounded, unique indices,
   read in increasing order. Short Cine files may probe every frame. Only the
   current and previous raw image are retained; no full-Cine image list is built.
3. **Change metric:** `mean(abs(B.astype(float32) - A.astype(float32))) / 255`.
   Only raw uint8 grayscale is supported in v1. Unsupported data is recorded as
   a per-file failure; no hidden conversion or Ref90 display transform is used.
4. Rank intervals by decreasing score, with earliest interval breaking ties.
   Select up to eight intervals, with midpoint separation at least
   `max(3, round(frame_count * 0.005))`. Zero-score intervals are skipped.
5. **Local refinement:** read consecutive frames only inside selected intervals.
   The peak is the **second frame** of the largest adjacent difference; ties
   choose the earliest pair. Record coarse endpoints and both local-pair indices.
   Refined peaks also obey the separation bound; rejected peaks are not backfilled.
6. Merge anchors and peaks by relative Cine path/frame index. Preserve every
   reason in `sample_reasons`; priority is the maximum applicable configured
   value (anchor 50, change 100). No peak ±1 context frames or artificial padding.

The default yields at most 19 unique candidates/Cine, possibly fewer. Decoding
counts include rereads during refinement; preview decoding is reported separately.
Memory for raw frames is independent of video duration. Metadata/timestamp tables
are supplied by CineReader. A long interval in a very long Cine can still require
many local reads; coarse sampling can miss short changes or cancellation between
interval endpoints. Peaks can reflect illumination/noise changes and have no
automatic scientific meaning.

TIME64 and relative timestamps come from `CineReader.build_frame_result`.
There is no nominal-FPS timing fallback. A one-frame Cine has fraction 0.

## CLI and output safety

```text
python scripts/build_annotation_queue.py --root "path/to/dataset" --output "outputs/annotation_queues/run/queue.json" --preview
```

`--config` selects another explicit config file. Recursion is default;
`--recursive` / `--no-recursive` are supported. `--preview` is optional.

All source size/mtime values are captured before decoding, checked after each
Cine and again at the end. Any change or disappearance immediately aborts.
Ordinary reader errors are isolated in `failed_files`. Non-Cine files are ignored.
No source-side cache, image, index, log, conversion or hash is written. Output
paths resolving inside the dataset are rejected, including symlink escapes.

Existing output queues resume status, notes and annotation links by stable ID.
A changed configuration/source identity or rebuild that would lose existing
items fails instead of silently erasing work. Choose a new output for resampling
with different parameters. This is single-user persistence, not a concurrent
multi-writer database.

Alongside the queue: `sampling_summary.json`, `sampling_summary.txt`, optionally
`queue_preview_contact_sheet.png` and `preview_diagnostics.json`. The sheet is
grouped by Cine and sorted by frame index. **REF90 DISPLAY PREVIEW — SAMPLING WAS
PERFORMED ON RAW PIXELS.** Preview uses one Cine-locked Ref90 gain; it is not
training data. Large sheets above 80 megapixels are refused. Preview failures
leave the previously saved queue intact. The source stat check detects size/time
changes, not malicious byte edits preserving both attributes.

## Queue JSON schema v1

Top level: `schema_version`, `queue_id`, name, `sampling_preset_id`, configuration,
`dataset_root_hint` (a name only), creation/update times, items, failed files and
per-Cine sampling reports. No absolute dataset root or image pixels are embedded.

Each item contains:

- `item_id`: first 24 hex characters of SHA-256 of UTF-8
  `relative_cine_path + ':' + frame_index` (case preserved, POSIX separators);
- relative Cine path, Cine ID/filename, frame count, size/mtime identity;
- frame index/fraction, raw TIME64, relative timestamp and timing status;
- sample reasons, local change score, coarse endpoints, local adjacent pair;
- priority, status, free-text notes, timestamps and optional annotation document
  reference relative to the queue's directory.

`cine_id` follows CineReader's filename-stem convention. Queue identity uses the
full relative path as well, so same-named Cine files in different folders remain
distinct. Annotation filenames additionally include a relative-path hash.

## Viewer workflow

Use **Queue → Open Queue...** then **Set Dataset Root...**. The local root is
never serialized. Missing or changed files are marked unavailable without
crashing; correcting the root rechecks availability. The queue dock can be hidden
through the Queue menu when more canvas space is needed.

Open Selected Item waits for Cine/frame loading before making it current.
Stale opens cannot mark a newer item's status. Same-Cine items navigate without
reopening the reader. Next/Previous Pending follows queue order (Cine, then frame)
without wrapping; priority remains a work-order hint. Select IN_PROGRESS items
explicitly to resume them. A loaded PENDING item becomes IN_PROGRESS; it never
becomes DONE automatically.

Statuses: **PENDING, IN_PROGRESS, DONE, SKIPPED, NEEDS_REVIEW**. Mark Done/Skipped/
Needs Review affects the actually displayed current item, not an unrelated list
selection. Add Note records a human note. Every operation immediately saves
atomically; errors warn and retain dirty state for Save Queue retry. Window close
or queue replacement is blocked if pending queue changes cannot be saved.

Before changing queue items, dirty annotations offer Save/Discard/Cancel.
Cancel leaves the Cine/item untouched. For same-Cine switching, Save keeps the
document; explicit Discard restores its last formal save (or an empty document
if never saved). Ordinary frame navigation continues retaining in-memory edits.

One Cine shares one AnnotationDocument across its queue frames. Default formal
annotations and autosaves live under the queue folder's `annotations/` directory.
Formal annotation Save links all items for that Cine to the document. Revisiting
another Cine loads its linked document, including immutable history. Documents
outside the queue folder may be saved but are not given nonportable links; save
inside the queue folder to make progress portable. Queue status is not an
annotation or scientific ground-truth approval, and does not imply annotation
Save. Save annotations explicitly before marking work complete.

## Scientific boundary and validation

Ref90/Raw/Manual/Auto remain display-only; annotation geometry stays in raw image
coordinates. Sampling does not alter annotations or classify physical events.
Future dataset export must split by **Cine / experimental run**, not randomly by
sampled frame; nearby frames remain highly correlated even after sparse sampling.

Unit tests cover anchor rounding, probe limits, float differences, refinement,
separation, merging, stat protection, error isolation, stable IDs, atomic JSON and
resume. Qt tests cover status persistence, same/different-Cine navigation,
dirty Cancel, shared document reload, unavailable files and stale requests.
