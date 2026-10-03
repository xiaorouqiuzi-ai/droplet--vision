# Cine Reader

Implemented on `feature/cine-reader`, pending review; not yet merged to main.
This feature covers raw input only: PIMS reading, random frame access, core
metadata, raw TIME64 and batch inventory. It performs no segmentation, event
analysis, measurements, plotting, image export or video conversion.

## Backend and read-only contract

`CineReader` lazily imports PIMS 0.7 when constructed. Importing `droplet_vision`
or `droplet_vision.cine` does not import PIMS or NumPy. The `cine` optional extra
declares `pims==0.7`; use the existing environment. Missing backend dependencies
raise `CineDependencyError`; the library never installs packages.

PIMS opens inputs in `rb`, and the raw tag reader also opens in `rb`. There are
no writes to Cine and no automatic exports. CLI writers reject Cine/CHD output
destinations. Opening parses headers, image offsets and timestamp/exposure
tables, without decoding any images. Use a context manager for reliable cleanup;
partial initialization failures close the backend handle as well.

```python
from droplet_vision.cine import CineReader

with CineReader("data/raw/example.cine") as reader:
    frame = reader.read_frame(0)  # independent ndarray copy by default
    for image in reader.read_frames([10, 2, 10]):
        pass  # generator preserves order and duplicates; one image at a time
    observation = reader.build_frame_result(0)
    metadata = reader.metadata.to_dict()
    timing = reader.timing_summary.to_dict()
```

Reader properties: `path`, `frame_count` (also `len(reader)`), `frame_shape`,
`pixel_dtype`, `frame_rate_header`, `compression`, `metadata`, `raw_time64`,
`timing_summary`, `closed`. `close()` is idempotent; reopen with a new instance.
Frame indices are zero-based and must satisfy `0 <= index < frame_count`.
Negative/out-of-range indices raise `IndexError`; noninteger indices raise
`TypeError`. Access after close raises `ValueError`.

`frame_shape` uses `(height, width[, channels])`, correcting PIMS 0.7's
width/height metadata ordering. `read_frame` returns PIMS-decoded pixels without
resize, normalization, contrast changes or grayscale conversion. PIMS itself
handles packed decoding and file orientation. `copy=False` is opt-in and makes
no storage ownership or writeability guarantee.

The adapter uses PIMS 0.7's private `_get_frame` pixel decoder to avoid requiring
timestamp/exposure metadata for pixel access. It wraps `_read_tagged_blocks`
with bounds validation before PIMS's own loop. This version-specific adapter
needs regression checks before changing PIMS versions.

## Core metadata

`CineMetadata.to_dict()` emits only declared fields, converting paths to strings,
datetimes to ISO strings, bytes by UTF-8 replacement decoding and NumPy scalars
to native scalars. Nonfinite floats become null; arbitrary objects are rejected.
The complete SETUP dictionary is never serialized.

Fields cover path/filename/file size, count, dimensions, bit depth, pixel dtype,
compression, header fps, shutter/frame delay in ns, post-trigger, camera serial,
camera/firmware/software versions, recording time zone, CFA, raw trigger TIME64,
PIMS trigger datetime/fraction, first image number, timestamp count and notes.
Bit depth uses nonzero `real_bpp`, otherwise bitmap `bi_bit_count`; it can differ
from the decoded storage dtype. PIMS trigger datetime is host-local; no inferred
timezone correction is applied. Prefer raw TIME64 for elapsed-time analysis.

`d_frame_rate` and `f_decimation` remain null, with notes stating
`not exposed by current PIMS parser`. The older integer `decimation` field is
not substituted for `f_decimation`. No extended SETUP struct is invented here.
Direct reader metadata includes its resolved local path; the inspect CLI
replaces this with the filename, and inventory emits relative paths only.

## Raw TIME64 and scientific timing

The small parser uses PIMS-provided `off_setup + setup_length` and
`off_image_offsets` to locate tags. Little-endian block headers contain uint32
size, uint16 type and uint16 more-tags. Only type 1002 payloads are interpreted
as uint64 TIME64. Unknown types are skipped by size. Bounds, minimum block size,
payload divisibility, truncation and tag-chain progress are checked; ambiguous
multiple Time Only blocks are rejected with `CineFormatError`. It is not a
complete Phantom parser. Raw integers retain all fractional/status bits.

Functions in `cine.timing`:

- `time64_delta_seconds(t1, t0)`: `(int(t1) - int(t0)) / 2**32`.
- `relative_times_seconds(sequence)`: elapsed seconds from the first timestamp.
- `frame_intervals_time64(sequence)`: adjacent signed differences in integer ticks.
- `summarize_timing(sequence, fps_header=None, expected_frame_count=None,
  mismatch_threshold=0.01)`: conservative diagnostics.

`TimingSummary` includes count, strictly increasing flag, repeated-value count,
adjacent backwards-step count, first-to-last duration, mean/median/population
standard deviation/min/max of adjacent intervals in seconds, timestamp fps,
header fps, ratio, status, threshold and warnings. Primary fps is
`(timestamp_count - 1) / duration`, equivalently `1 / mean(dt)`, never `mean(1/dt)`.
Ratio is header / timestamp fps. Mismatch is `abs(ratio - 1) > threshold`.

Absent/insufficient, duplicate, backwards or count-mismatched timestamps yield
TIMING_UNKNOWN; structurally unusable sequences have no reported fps. Numeric
agreement also remains TIMING_UNKNOWN. Only mismatch can be detected
automatically; no path promotes timing to VALIDATED. No external-validation
override is implemented in this version.

`build_frame_result` creates a pixel-free record with raw TIME64, elapsed time,
fps provenance and status. All segmentation/state fields remain None. Count
mismatches suppress per-frame timestamp mapping; nonmonotonic sequences retain
raw matched-frame values but suppress elapsed time. `cine_id` defaults to the
filename stem, so callers must disambiguate duplicate basenames across runs.

There is **no frame-index / nominal-fps fallback**. The observed test file has
8146 header fps versus approximately 4073.32 timestamp fps. This remains
TIMING_MISMATCH_UNRESOLVED; elapsed event times remain provisional. Follow
[timing_policy.md](timing_policy.md); agreement with PIMS is not physical timing
validation, and raw low status bits are never silently cleared.

## Inventory and CLI

`discover_cine_files(root, recursive=True)` finds case-insensitive `.cine` suffixes
in deterministic relative-path order. `inspect_cine(path, root=None, strict=False,
compute_hash=False, mismatch_threshold=0.01)` inspects one file. `build_inventory`
uses the same options and returns one row per file, closing each reader before
opening the next. By default errors become `readable=false`, `error_type` and
`error_message`; `strict=True` raises immediately. `readable=true` means headers,
index and timing were inspected, not that every image payload was decoded.
An invalid scan root itself is an error.

Rows include relative_path, filename, file_size_bytes, readability/error fields,
frame_count, width, height, bit_depth, pixel_dtype, compression, fps_header,
fps_timestamp, fps_ratio, timestamp_count, timestamps_monotonic,
duplicate_timestamp_count, non_monotonic_count, duration_timestamp_s,
interval_mean_us, interval_median_us, interval_std_us, interval_min_us,
interval_max_us, timing_status, shutter_ns, post_trigger, frame_delay_ns, serial,
camera_version, firmware_version, software_version, recording_time_zone, cfa,
d_frame_rate, f_decimation, sha256, notes and warnings.

`write_inventory_csv(rows, path)` writes nulls as empty cells and list fields as
JSON. `write_inventory_json(rows, path)` writes a schema_version and records.
Default portable mode omits absolute scan roots. An explicit
`include_absolute_root=True, scan_root=...` opts into storing a local root.
SHA-256 is disabled by default; enabling it streams 1 MiB chunks through the
entire file and can be expensive. Nothing hashes or decodes pixels by default.

```console
python scripts/inspect_cine.py --input data/raw/example.cine --json outputs/inspect.json
python scripts/build_cine_inventory.py --root data/raw --csv outputs/inventory.csv --json outputs/inventory.json
```

Inventory CLI options: `--no-recursive`, `--strict`, `--hash`; at least one of
`--csv`/`--json` is required. Library internals use logging (quiet by default);
CLIs print summaries. Outputs are local ignored artifacts and should not enter Git.

## Tests and limitations

Pure unittest tests use synthetic timestamps, tiny tagged-block fragments
(not fabricated complete Cine files), temporary discovery files and mocked
backends. No real Cine, NumPy or PIMS is required for pure tests.

PowerShell opt-in integration setup (choose your own local path):

```powershell
$env:DROPLET_VISION_TEST_CINE = (Resolve-Path 'data/raw/example.cine').Path
python -m unittest discover -s tests -v
Remove-Item Env:DROPLET_VISION_TEST_CINE
```

Without that environment variable, integration is skipped. Integration checks
random frame values/copy isolation, shape/dtype, bounds, timestamp counts,
FrameResult, close/reopen and all PIMS `get_time_to_trigger()` relative times.
The 2 microsecond tolerance is a parser cross-check tolerance, **not experimental
measurement uncertainty**. It has no filename-specific assertions.

Local smoke artifacts live under ignored `outputs/cine_reader_smoke/`.
No original Cine is copied. This feature has been smoke-tested on one supplied
monochrome uncompressed Cine; other cameras, color/compressed files, packed bit
depths and older SETUP layouts need independent validation. PIMS limitations
still apply. The tag parser does not validate every image payload, repair
timestamps, interpret status bits or resolve the experimental timing mismatch.
Inventory retains paths/rows and each reader's metadata tables in memory;
memory scales with file count and timestamps/index size, not decoded video size.
