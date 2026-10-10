# Cine Viewer

Implemented read-only viewing and display controls. Start with
[Getting Started](getting_started.md); drawing operations belong in the
[Annotation Editor guide](annotation_editor.md).

## Open and Close

From the source root, launch `launch_viewer.cmd` or `python scripts/launch_viewer.py`.
File → Open Cine (Ctrl+O) opens through CineReader, asynchronously. A bounded LRU
cache holds raw decoded frames (default 64); no whole-video pixel preload occurs.
Metadata/offset/TIME64 tables may be read at opening. Stale async responses are
ignored when navigating or switching Cine.

File → Close Cine releases the current source. Dirty annotations offer
Save/Discard/Cancel. ViewerSession/bookmarks require their own explicit save.
Shutdown waits for outstanding reader I/O; a blocked filesystem operation has no
hard cancellation. No source-side cache or annotation is written.

## Interface and Metadata

The left scrollable panel contains Image information, Timing information, Camera
information, Current frame, Display, Annotation Scheme, Current Annotation Data
and Current frame annotations. Values wrap, are selectable, and retain full TIME64
integers. Unknown metadata is shown as unknown, not invented.

The center is the image canvas. The right workspace holds annotation operations;
Queue and bookmarks remain separate docks. Menus are File, Annotation, Queue,
View, Model, Settings, Functions, Help. Language switches live; About shows software version,
repository/author information and the project icon.

## TIME64

Current-frame raw TIME64, relative timestamp and timing status come from FrameResult.
Relative time is displayed in seconds with nine decimal places when available.
Header FPS, timestamp-derived FPS and their ratio are diagnostics, not competing
automatic choices of scientific time.

**Never replace TIME64 with frame_index / header FPS.** Some validated recordings
show unresolved disagreement; missing/invalid timing is retained explicitly.
Software regression cannot establish experimental timing validity. See the
[timing policy](timing_policy.md) and [reader details](cine_reader.md).

## Navigation and Playback

| Control | Result |
| --- | --- |
| Fixed buttons ±1 / ±10 / ±100 / ±1000 | Jump by the stated frame count, clamped |
| Left/Right; Shift+Left/Right | ±1; ±10 |
| PgUp/PgDown; Ctrl+PgUp/PgDown | ±100; ±1000 |
| Home / End | First / last frame |
| Slider / spinbox | Seek frame index; slider requests debounce for 50 ms |
| Upper human marker | Click to jump; hover for object/state information |
| Space / Play | Toggle wall-clock-based review playback |

**Review Speed (frames/s) / 检阅速度（帧/秒）** offers 1, 2, 5, 10, 15, 20, 30,
60, 120, 240, 500, 1000; default 10. The value means source frames advanced per
real second, not displayed images per second or experimental acquisition FPS.

On Play, the Viewer records the displayed frame and a monotonic clock origin.
The next target is `start_frame + floor(elapsed_seconds * review_speed)`, clamped
to the Cine range. At 1000 frames/s, five real seconds means approximately +5000
source frames; a 32196-frame Cine takes about 32.2 seconds to scan from frame 0,
plus any final decode delay. The GUI need not render 32196 images.

The timer polls at up to approximately 60 Hz. While a decode is busy, only one
latest clock target is retained; no intermediate-frame request queue is built.
An admitted decode may finish and display while the clock advances. The next
idle tick requests the newest target, preventing slow I/O from starving display.
Requests invalidated by Pause, manual seeks or Cine changes are ignored on return.
High-speed review may skip intermediate frames to maintain the requested scan rate;
low rates are generally frame-by-frame, but can also skip after stalls.

The timeline, frame label and TIME64 metadata reflect successfully presented
frames. Pause invalidates pending playback results. Resume resets the origin to
the currently displayed frame; changing speed also resets this origin. Timeline,
marker and fixed jump navigation pause review. The final frame is displayed and
playback stops without wrapping. +1000 jumps and 1000 frames/s remain independent.
This UI setting never computes or modifies scientific timestamps or annotations.

Upper markers retain native slider behavior outside their 15-pixel hit width
and top strip. Same-column markers are painted once; click selects the represented
frame nearest the current position. Tooltip identifies aggregation and lazily
resolves human Object count and localized State names. Pure predictions are excluded.
See [marker details](annotation_editor.md#timeline-markers).

## Auto Fit, Zoom and Pan

Auto Fit defaults ON for each Cine. First valid image, dimension changes and view
resize fit the image; ordinary frame changes preserve manual view state. Wheel
or +/- zooms; middle drag pans. Manual zoom/pan disables Auto Fit. F or the Auto Fit
control refits and re-enables it. All scene coordinates remain raw image coordinates.

## Display Modes

**DISPLAY TRANSFORM != SCIENTIFIC PIXEL DATA.** Display settings rerender the
cached raw frame, without decoding it again. Metadata statistics are not silently
replaced with enhanced values.

| Mode | Behavior |
| --- | --- |
| Raw | Independent display copy; uint8 grayscale/RGB values unchanged |
| Photometric Normalization (Ref90) / 亮度标准化（Ref90） | Default, one locked gain for the Cine |
| Manual | Brightness -100…100, contrast 0.25…4, gamma 0.2…5 |
| Auto contrast | Percentile stretch, default 1–99; constant images safely retain reference display |

R selects Raw, P Ref90, E the previous enhanced mode. Reset selects Raw and
restores neutral/manual/default percentiles without changing frame, zoom or annotations.
Only one transform is active; Manual is not stacked onto Ref90. Raw uint16 display
uses a fixed `//256` uint8 mapping; that is display-only, not preservation of full
16-bit intensity on screen. RGB/uint16 do not use the Ref90 v1 estimator.

### Photometric Ref90: default Cine-locked display

The frozen [preset](../configs/photometry/photometric_ref90_v1.json) remains
`photometric_ref90_v1`. The asynchronous worker uses raw frame
`round((frame_count - 1) * 0.03)`, clamped, to estimate one P90-based gain.
It stays fixed across navigation/playback. Reopen or **Recalculate Reference**
explicitly recalculates; a mode change alone does not.

Advanced Display information shows preset ID, reference index/P90, target, gains,
saturation and QC. Warnings do not automatically change gain. Invalid reference
or unsupported pixels produces a visible Raw fallback. In package mode, exported
gain provenance is used and recalculation is unavailable; Cine is not accessed.

Manual uses normalized pixels, contrast around mid-gray, brightness offset,
clipping, then gamma and uint8 rounding. Auto stretches the configured percentiles;
neither is physical intensity correction. Detailed boundaries and preset provenance
are in [preprocessing policy](image_preprocessing_policy.md) and
[photometric presets](photometric_presets.md).

## Raw Export

File → Export Current Frame (Ctrl+E) saves raw PNG, regardless of display mode.
Default filename is `<cine>_frame_<index>.png`, under `outputs/viewer_frames/`.
Current uint8 grayscale export is verified by reopening and comparing pixels.
It contains no overlay or Ref90 enhancement. There is no separately implemented
enhanced-preview export command.

## Bookmarks and ViewerSession

B bookmarks the current frame; the Annotation menu offers bookmark notes/tags and
session notes. Double-click a bookmark to navigate. Bookmarks are navigation aids,
not Object annotations or Ground Truth.

Ctrl+S saves ViewerSession, normally under `outputs/viewer_sessions/`. Ctrl+L
loads it and asks for the matching Cine when needed. It retains last frame,
bookmarks, notes, display and playback/view preferences, without annotation records.
New sessions store `ui_state.review_speed_frames_per_second`; sessions containing
the legacy `review_playback_fps` key still load. The new key takes precedence.
Cine filename/size/count checks are not a whole-file hash. Reopening recalculates
the Cine reference rather than trusting an old saved gain against changed input.

Unsaved session notes/bookmarks do not have AnnotationDocument dirty protection;
save them explicitly. [Annotation saving](annotation_editor.md#saving-history-and-recovery)
is separate.

## Annotation Package Mode

Functions → Open Annotation Package… opens PNG-backed frames, with a visible mode title and
available-frame count. Sparse target/context markers are distinct from human-work
markers. Missing frames produce a message, not a black/forged frame. Single-step
playback follows available frames, so it must not be interpreted as a complete
experimental sequence. Use [annotation package instructions](annotation_package.md).

Uniform sampling creates a single-Cine package with exactly N unique targets when F ≥ N,
including both endpoints. Empty annotation snapshots are supported. The left panel
shows target, annotated/reviewed and remaining counts. Opening a frame alone does
not count as completion. Legacy `.dvrpkg` remains readable; new exports use `.dvapkg`.

## Implementation and Limits

CineController serializes reader/cache work and rejects stale requests. Cached
arrays are read-only; independent display arrays become QImage. Qt belongs to
UI, not the annotation/Cine data contracts. Raw grayscale, Ref90, raw export and
TIME64 boundaries are tested, but not every Phantom variant is validated.
No inference, tracking, scientific measurement, mask brush or automatic event
classification is exposed as a finished Viewer feature.

Related: [Editor](annotation_editor.md) · [Cine Reader](cine_reader.md) · [Index](README.md).
