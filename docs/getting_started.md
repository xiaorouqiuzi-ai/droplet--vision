# Getting Started

Use the Windows source checkout. No Cine needs to be copied into the repository;
a reviewer can start with only a `.dvrpkg`.

## Requirements and Installation

Use Python 3.12 in a dedicated environment. VisionLab is the tested development
environment; exact versions are in [Installation](../README.md#installation).
No GPU, Torch, YOLO or OpenCV is needed. Keep `configs/` with the source checkout.

```powershell
git clone https://github.com/xiaorouqiuzi-ai/droplet--vision.git
cd droplet--vision
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e ".[cine,ui]"
python -m pip check
python -c "import sys; print(sys.executable); print(sys.version)"
```

In CMD use `.venv\Scripts\activate.bat`. If activation is unavailable, replace
`python` with `.venv\Scripts\python.exe`. Use the same interpreter for installation,
launch and tests. Existing verified environments do not need reinstallation.

## Launch

From the repository root:

```powershell
python scripts/launch_viewer.py
```

Alternatively run `launch_viewer.cmd` in the activated environment. For double-click
use without activation, create `configs/viewer.local.txt` containing only your
environment's full `python.exe` path, without quotes. This file is Git ignored.
The launcher checks `DROPLET_VISION_PYTHON`, that file, repository-local
`VisionLab/Scripts/python.exe`, then `VIRTUAL_ENV`. An old local setting takes
precedence over activation: update it if switching environments.

For a local shortcut, use your environment's `pythonw.exe`, pass the full local
path of `scripts/launch_viewer.py`, set the working directory to the repository,
and choose `src/droplet_vision/ui/assets/icons/planico.ico`. Local paths belong
in the shortcut, never versioned configuration. Use the console launcher for errors.

## Open Cine

Choose **File / 文件 → Open Cine / 打开 Cine**. Wait for asynchronous loading
before drawing. The left panel shows full TIME64 and relative time. A failed
Ref90 reference falls back to Raw with a message. Cine remains read-only.
For a package, use **File → Open Review Package…** instead.

## Auto Fit and Navigation

Auto Fit defaults on for a new Cine. Resize to refit; wheel or +/- zooms and
middle-button drag pans. Manual view changes turn Auto Fit off; **F** fits and
re-enables it.

Fixed buttons jump ±1/10/100/1000. Shortcuts: Left/Right, Shift+Left/Right,
PgUp/PgDown, Ctrl+PgUp/PgDown. Home/End selects first/last frame. Click an upper
annotation triangle to jump; hover for object/state details. Space toggles
review playback. **Review Speed (frames/s) / 检阅速度（帧/秒）** controls how many
source frames advance per real second. At 1000, the view advances approximately
5000 frames in five seconds, skipping intermediate images as needed. It does not
require 1000 rendered images per second. Pause/resume uses the displayed frame as
its new origin; manual navigation pauses playback. Review Speed is independent
of +1000 jumps and scientific TIME64 timing.

## Display Modes

Default **亮度标准化（Ref90） / Photometric Normalization (Ref90)** uses one locked
gain per Cine. **R** selects Raw, **P** Ref90, **E** the previous enhanced mode.
Manual brightness/contrast/gamma and Auto percentile are independent modes.
Display changes never alter raw pixels, geometry or TIME64.

## First Annotation

1. Select an **Annotation Scheme** on the left and click **Apply**.
2. Choose the unlocked **Manual** drawing layer on the right.
3. Click **Parent droplet / 父液滴**; compatible Polygon is recommended.
4. Click at least three vertices. Click the first point, double-click or Enter
   to **close**. The dashed outline remains temporary.
5. Adjust square vertices or hollow midpoint handles.
6. **Confirm / Enter** creates a solid persistent annotation.
7. Select applicable Frame States. More States is multi-select. Use Uncertain
   and Notes when evidence needs review; inspect neighbors for dynamic judgments.

Point creates a record on click. Wand proposes editable raw-pixel polygon drafts
and also requires Confirm. See the [editor tutorial](annotation_editor.md).

## Save and Reopen Annotations

To reuse a droplet support rod, select **载滴杆 / Droplet support rod**, confirm
one or more polygons, and check **Apply to entire Cine** (shown only for this
label). One Cine-level template is projected across frames without duplicating
records. Editing a projection creates a local override; deleting that override
restores the template. Save the AnnotationDocument to retain templates/overrides.
Unchecking disables projection without deleting history. The current annotation
list provides an eye toggle (Session-only visibility) and right-click deletion
(deactivation with Undo/Redo). Hidden records still count as annotated frames;
pure template projections do not. Save ViewerSession separately for visibility.
See [template details](annotation_editor.md#cine-level-droplet-support-rod-template).

**Annotation → Save Annotations / Ctrl+Shift+S** saves under
`outputs/annotations/<cine>.annotations.json` by default. **Current Annotation
Data** shows the actual saved location, or only a suggested location before
first save. Ctrl+S saves ViewerSession, **not annotation records**.

Reopen the matching Cine, then **Annotation → Open Annotations…** (Ctrl+Shift+O
or Ctrl+Alt+O). Identity/dimensions must match. Dirty documents offer
Save/Discard/Cancel; Cancel keeps work. Autosave does not replace formal Save.

## Queue Basics

Build a queue using the [sampling CLI](frame_sampling_queue.md#cli-and-output-safety).
Queue → Open Queue…, Set Dataset Root…, then Open Selected Item or Next Pending.
Save annotations before Mark Done. Reopen the same queue and set its root to
resume. Queue status is work progress, not scientific approval.

## Review Package Basics

Save the original annotation document, then export selected frames and context.
A reviewer opens the `.dvrpkg`, edits and saves a new `_reviewed.dvrpkg`.
Import it into the original document: Manual records stay intact. Follow the
[two-person workflow](portable_review_package.md) before sending data.

## Troubleshooting

| Symptom | Check |
| --- | --- |
| Launcher cannot find Python | Activate the environment or fix its ignored local setting |
| Missing Qt/PIMS | Verify `sys.executable`; install the matching extras there |
| No normal GUI window | Remove a leftover `QT_QPA_PLATFORM=offscreen` environment setting |
| Drawing disabled | Wait for loading; choose an enabled compatible label and unlocked Manual/Reviewed layer |
| Draft disappears on navigation | Close and Confirm before changing frame |
| Timing warning | Investigate acquisition; Review Speed cannot repair timing |
| Missing package frame | Use available frames/targets; packages are intentionally sparse |
| Dirty after Undo | History/audit changes still require saving |
| Document mismatch | Locate the matching Cine/document; do not rename raw data to bypass checks |

Related: [Viewer](cine_viewer.md) · [Annotation Editor](annotation_editor.md) · [Index](README.md).
