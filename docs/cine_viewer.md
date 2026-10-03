# Cine Viewer UI v1 and annotation workstation foundation

Implemented on main.

Display Enhancement v1 is implemented on main, with Raw, Manual and Auto
percentile display modes. These three paths remain independent:

- Display pipeline: raw frame → independent display transform → QImage.
- Scientific pipeline: raw frame → scientific measurement.
- Annotation geometry: raw image coordinates, independent of display settings.

Launch from a source
checkout with `python scripts/launch_viewer.py [--cine path/to/sample.cine]`.
VisionLab Python 3.12 is the current environment; see README for exact tested
versions. The UI only opens input through `droplet_vision.cine.CineReader`.
No Qt dependency enters core, Cine, annotations or inference interfaces.

## Responsibilities

`ui.app` starts Qt; `MainWindow` composes metadata, taxonomy, layers, bookmarks,
Graphics View canvas, timeline and transport widgets. `CineController` owns a
single worker pool and serializes all reader/cache access. Only one I/O task is
active and one newest pending task is retained. Tokens reject stale opens,
frame responses and failures. Closing invalidates outstanding requests; app
shutdown waits for running I/O before closing the file handle.

`FrameCache` stores raw arrays with a configurable default limit of 64 frames.
It is cleared across Cine changes; raw cached arrays are read-only. UI display
copies data into an independently owned QImage. No complete video is loaded.
Opening metadata/timestamps is also asynchronous. Slider movement debounces
for 50 ms; navigation buttons/spinbox request immediately. While a newer slider
intent is pending, an older response cannot reset the slider.

Canvas uses QGraphicsView/QGraphicsScene. Wheel or +/- zooms; middle drag pans;
F fits the image. Overlay scene coordinates equal original image coordinates.
2D uint8 and RGB uint8 display unchanged. uint16 grayscale display divides by
256 into uint8; this is a fixed display-only mapping, not normalization of raw
data. Scientific values and PNG export continue to use raw arrays.

The unchanged display above is the **Raw** reference mode. The Display panel
now also offers Manual and Auto contrast; these operate on independent copies
between the raw cache and QImage. `droplet_vision.display` uses NumPy and has no
Qt dependency. CineReader and FrameCache retain raw pixels. Changing settings
rerenders only the current cached image, without requesting or decoding a frame.

## Display enhancement

**DISPLAY TRANSFORM != SCIENTIFIC PIXEL DATA**

Display-enhanced pixels must not replace raw pixels for scientific grayscale
statistics, cavity intensity analysis, physical interpretation or raw frame
export. Bright/dark appearance alone does not establish phase identity.
Adjusting settings uses the current raw cached frame without rereading Cine,
modifying FrameCache, altering annotations or changing timestamps.

- Raw: uint8 grayscale/RGB values are preserved exactly in an independent array.
- Manual: normalize the display reference to `u = pixel / 255`, then compute
  `v = clip((u - 0.5) * contrast + 0.5 + brightness, 0, 1)`, followed by
  `round_to_even(255 * v**gamma)` as uint8. UI Brightness -100..100 maps to
  -1..1; Contrast is 0.25..4; Gamma is 0.2..5. Gamma 1 is neutral. With this
  display formula, a smaller gamma brightens midtones; it is not a physical
  correction. Manual parameters are inactive in Raw/Auto modes.
- Auto contrast: compute NumPy's linear percentiles over the display reference
  (default 1 and 99), map low to 0 and high to 255, clip and round to uint8.
  RGB uses a shared range over all channels, not independent channel balancing.
  If high <= low, retain the Raw reference and show an insufficient-range
  diagnostic, avoiding division by zero for constant images. A narrow but
  positive range is safely stretched and clipped. Changing a percentile past its partner adjusts the partner by
  0.1 percentage point so low stays below high.

uint16 retains the existing fixed `//256` reference mapping before either
enhancement. This is deliberately limited display support, not full-depth
scientific processing. Inputs, dtype and shape remain unchanged; outputs are
independent uint8 arrays with the same geometry. No resampling takes place.

R switches to Raw; E restores the previous non-Raw mode (initially Manual).
Reset Display restores Raw, brightness 0, contrast/gamma 1 and percentiles 1/99,
without resetting frame position, zoom/pan, overlays, bookmarks or notes. The
status bar always names the display mode and marks active enhancement. Display
diagnostics are separate from the raw Metadata panel. Export Current Frame
always exports raw pixels, regardless of the visible mode; its tooltip says
"Exports raw frame pixels, not display-enhanced preview."

ViewerSession saves `ui_state.display` using DisplaySettings serialization.
Opening a new Cine starts in Raw; a matching loaded session restores its display
state. Old sessions without this field use defaults. Invalid/unavailable settings
produce a warning and fall back to Raw. No display settings enter annotation
geometry or scientific metadata. Modes use extensible string IDs and a display
backend registry; registering a backend before constructing the panel adds its
mode to the selector. Additional backend-specific controls remain future work.
No CLAHE, histogram widget or Display Preview export is implemented in this update.
See [image preprocessing policy](image_preprocessing_policy.md) for the required
separation from model preprocessing and scientific intensity analysis.

## Navigation and timing

Left/Right step one; Shift+Left/Right step ten; PageUp/PageDown step 100;
Home/End jump to first/last. All requests clamp to valid indices. Space toggles
review playback. Review Playback FPS offers 1, 2, 5, 10, 15, 20, 30 (default 10).
QTimer never uses header or timestamp-derived experimental frame rates. Playback
waits for a loaded frame before advancing and stops at the end; slow storage
can make effective playback slower than the chosen review speed.

Metadata shows only core fields and current frame index, raw TIME64 and relative
timestamp. Time comes from `FrameResult`, never index/header fps. The tested
Cine still reports 8146 versus approximately 4073.320013 fps and
TIMING_MISMATCH_UNRESOLVED. Software regression and UI smoke tests do not resolve
physical timing validity. No optical feature is automatically assigned phase
identity or classified as puffing/micro-explosion. No physical volume is computed.

## Open taxonomy and geometry

`configs/annotations/default_taxonomy.json` contains starting examples only.
`AnnotationLabel.label_id` is an arbitrary stable string, independent of the
scientific `ObjectType` enum. `display_name`, group, enabled, allowed geometry
types and attributes are configurable. Add labels and restart; alternatively
pass `--taxonomy`. Tests load `experimental_feature_x`, which has no dedicated
UI code. Disabled labels are not offered for selection.

All persisted geometry uses **image pixel coordinates**, top-left origin,
x = column, y = row, with subpixel values allowed. Never persist widget/zoom
coordinates. Supported schema vocabulary:

| Type | Geometry convention | v1 read-only rendering |
| --- | --- | --- |
| point | `{"point": [x, y]}` | Yes |
| bbox | `{"bbox": [x, y, width, height]}` | Yes |
| polygon | `{"points": [[x, y], ...]}` | Yes |
| polyline | `{"points": [[x, y], ...]}` | Future |
| ellipse | `{"center": [x, y], "radii": [rx, ry], "rotation_deg": 0}` | Future |
| mask | JSON descriptor, e.g. `{"encoding": "external", "relative_path": "masks/example.png"}` | Future |
| keypoints | `{"points": [{"name": "tip", "x": 1, "y": 2, "visible": true}]}` | Future |

Schema accepts JSON geometry and validates type/finite serialization; full
geometry topology and optical validity validation belong to future editors.
The OverlayManager dispatches by geometry renderer registry, never label/model
name. Canvas consumes AnnotationLayers; future mask renderers can be registered.
AnnotationTool/ToolRegistry define activate, deactivate, mouse press/move/release,
commit and cancel. Polygon, box, ellipse, point, polyline, mask-brush and keypoint
tools can register factories. Future editing must use QUndoStack/command pattern;
v1 has no editable geometry tools or undo commands.

## Layers, provenance and human review

Layer roles include prediction, manual, reviewed, ground_truth, measurement and
auxiliary. UI has visible and locked toggles, current-frame items/count and
selected taxonomy label. Locked is policy state for future editors; v1 overlays
are all read-only, including unlocked layers.

Future workflow: AI prediction → Prediction Layer → human review →
Accept / Edit / Reject → Reviewed Layer → Ground Truth.

AnnotationStore owns deep copies and disallows replacement of existing IDs.
Review creates a new record with `derived_from`, reviewer, decision, timestamps
and a new ID. Original model_id/confidence/geometry remain in the source record;
manual derivatives do not pretend to have a model confidence. This permits
model error/correction and hard-case comparison. Stored records returned to
callers are copies. Direct dataclass objects are transport values, not immutable
database objects; downstream persistence/editors must use the store contract.

PredictionProvider defines `predict(cine_id, frame_index, image) -> AnnotationLayer`.
Future YOLOAdapter/UNetAdapter must provide source/model provenance, preserve raw
images and feed a prediction layer. No Torch/Ultralytics imports or packages are
introduced. No prediction/editing commands are exposed as completed functionality.

## Bookmarks, sessions and export

B adds a bookmark for the currently displayed frame. Annotation menu also
supports arbitrary note/tags and session notes. Bookmark is a navigation aid,
not segmentation ground truth. Double-click to navigate to its frame.

Save Session As defaults to `outputs/viewer_sessions/<cine_stem>.json`. Portable
JSON includes filename, size, frame count, last displayed frame, bookmarks with
raw/relative timestamps, notes, review playback setting and optional relative
layer references. Explicit local_only data is excluded from portable saves.
Loading asks the user to locate the Cine when necessary and checks filename,
size and frame count. It does not depend on an absolute machine path. Identity
checks do not establish byte-identical content; automatic full-file hashing is
intentionally absent. Annotation layer content uses the separate annotation
store and is not embedded in v1 viewer sessions. Non-JSON session destinations
are rejected to prevent overwriting a Cine.

Ctrl+O opens, Ctrl+E exports one displayed raw frame, Ctrl+S saves session,
Ctrl+L loads session, Ctrl+Q exits. File dialogs use Qt for consistent behavior
across platforms. PNG default name is `<cine_stem>_frame_<index:06d>.png`, under
ignored `outputs/viewer_frames/`. uint8 grayscale export is pixel-exact and is
verified by reopening the PNG. There is no automatic bulk export or hashing.
Unsaved sessions/bookmarks are currently in memory; save before changing Cine
or closing the app (no autosave/unsaved-changes prompt in v1).

## Validation and current limits

Pure annotation/store/session tests do not require Qt. UI tests use
`QT_QPA_PLATFORM=offscreen`. Real tests run only with `DROPLET_VISION_TEST_CINE`
set, including frame 0, middle/requested 16098, last frame, PNG equality and
close/reopen. File size/mtime are checked unchanged. Logs and local UI smoke
artifacts are in ignored `outputs/viewer_smoke/`.

Validated scope is one supplied monochrome Cine and synthetic UI geometries;
other cameras/packed/color formats require broader validation. Full annotation
editing, mask overlays, sampling, dataset export, model inference and scientific
measurement/event analysis remain future work. Default taxonomy discovery
currently assumes a source checkout; distributing configs in a wheel is future
packaging work. UI shutdown waits for the current reader operation; there is no
hard cancellation of a blocked filesystem call.
