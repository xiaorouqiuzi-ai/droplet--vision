# Droplet Vision

Repository: `droplet--vision` · Python package: `droplet_vision`

Quantitative analysis of high-speed suspended-droplet experiments, preserving
the original research focus on droplet deformation and extending it to:

- parent-droplet evolution;
- internal cavity/bubble evolution;
- puffing and micro-explosion;
- daughter-droplet formation and secondary atomization.

Pipeline:

**Cine → Segmentation → Tracking → State/Event Analysis → Scientific Metrics → Statistical Dataset**

Cine infrastructure decodes frames before segmentation. Statistical outputs
support figures and papers. YOLO / deep learning are segmentation tools, not
physical conclusions. No trained models or implemented segmentation pipeline
are supplied in this scaffold.

## Project status

| Phase | Scope | Status |
| --- | --- | --- |
| 1 | Cine reader / metadata / TIME64 / inventory | Implemented (v1) |
| 2 | Classical CV baseline | Planned |
| 3 | AI segmentation | Planned |
| 4 | Scientific measurement and event analysis | Planned |

Cine Viewer UI v1 is implemented on `feature/cine-viewer-ui` for review, not
merged into main. Its long-term target is the **Droplet Annotation Workstation**:
Cine → Frame Viewer → Frame Sampling → Manual Annotation → AI Prediction Overlay
→ Human Review / Correction → Ground Truth → Dataset Export → YOLO / U-Net
→ Scientific Measurement → Event Analysis. Viewer v1 does not perform inference
or physical event classification.

## Environment Setup

The project is currently developed and validated with Python 3.12.

### Current tested development environment

These versions describe the current tested development environment, not a
permanent dependency lock for the project.

- Python 3.12.10
- NumPy 2.0.2
- Pillow 11.3.0
- PIMS 0.7
- ImageIO 2.37.2
- tifffile 2024.8.30
- PySide6 6.10.2

This combination is validated for current Cine Reader and Viewer v1 smoke tests
with a real Phantom Cine: random frame access, TIME64 parsing, metadata,
inventory, Qt frame navigation, timestamp display, export pixel equality and
close/reopen. This is validation of software behavior on the tested Cine, not a
resolution of its timing mismatch or validation of all Phantom formats.

Create a dedicated environment using Python 3.12; do not install project
dependencies directly into system Python:

```console
python -m venv VisionLab
```

Windows CMD activation: `VisionLab\Scripts\activate`. In PowerShell use
`.\VisionLab\Scripts\Activate.ps1`, or invoke `VisionLab\Scripts\python.exe`
directly. On Bash use `source VisionLab/bin/activate` when created on POSIX.
Check `python -c "import sys; print(sys.executable); print(sys.version)"` before
running installation or tests. Use that same interpreter throughout.

The following single-line installation command works in PowerShell or Bash
after activating the dedicated environment (already verified environments do
not need reinstallation):

```console
python -m pip install numpy==2.0.2 pillow==11.3.0 pims==0.7 imageio==2.37.2 tifffile==2024.8.30 PySide6==6.10.2
python -m pip check
```

Expected: `No broken requirements found.` This was confirmed in VisionLab.
No packages were installed or changed during Viewer v1 development.

Optional Jupyter kernel setup:

```console
python -m pip install ipykernel
python -m ipykernel install --user --name visionlab --display-name "Python (VisionLab)"
```

Jupyter is not a Viewer dependency. OpenCV, scikit-image, SciPy, pandas,
matplotlib, PyTorch and Ultralytics YOLO are not currently required; introduce
them only when the relevant modules are developed and separately approved.
Base package dependencies stay empty; `cine` and `ui` are optional extras.

### Launch Cine Viewer

On Windows, double-click **`launch_viewer.cmd`** in the repository root.
For an existing external VisionLab environment, create the ignored local file
`configs/viewer.local.txt` containing only its full `python.exe` path (without
quotes). This local file is not committed. The launcher checks, in order:
`DROPLET_VISION_PYTHON`, that local file, `VisionLab/Scripts/python.exe` inside
the repository, then the activated virtual environment. It does not install
dependencies or fall back to system Python. If no interpreter is found, it
shows setup instructions. Keep the console open while using the viewer;
startup errors remain visible there.

Arguments are supported, for example:

```console
launch_viewer.cmd --cine path/to/sample.cine
```

From the repository root in VisionLab:

```console
python scripts/launch_viewer.py
python scripts/launch_viewer.py --cine path/to/sample.cine
python scripts/launch_viewer.py --taxonomy configs/annotations/default_taxonomy.json
```

The taxonomy is an open JSON label list, not a closed enum. Add a new `label_id`
and restart the Viewer to show it, without editing UI Python. See
[Viewer and annotation architecture](docs/cine_viewer.md).

## Organization

`src/droplet_vision` holds reusable interfaces and future processing modules;
`configs` holds portable examples; `docs` holds scientific policies; `tests`
holds small standard-library tests. `data`, `models`, `training`, `outputs`,
`notebooks`, and `scripts` document their intended roles.

Start with [architecture](docs/architecture.md), [model strategy](docs/model_strategy.md),
[annotation guidance](docs/annotation_guideline.md), and [timing policy](docs/timing_policy.md).

## Environments and checks

VisionLab is the current Cine/UI development environment; the previous
Python 3.9 environment is not required. Keep future GPU training/inference
separate and exchange stable records through backend-neutral interfaces.
Core interfaces retain Python >=3.9 compatibility and do not import Qt/PIMS.
UI smoke tests target the tested Python 3.12 environment above.
From the repository root in VisionLab:

```console
python -m unittest discover -s tests -v
python -m compileall src scripts
```

Local paths belong in ignored local configuration, never machine-specific
versioned settings. Raw Cine files, exported datasets, and weights stay outside
Git; see [data policy](docs/data_policy.md).

## Update summary

- Initial scaffold: established object/state separation, optional measurement
  interfaces, annotation guidance and provisional timing/validation policies.
- Cine Reader v1 is implemented on main: read-only random frame access,
  whitelisted metadata, bounded raw
  TIME64 extraction, conservative timing summaries, portable CSV/JSON inventory,
  CLI entry points and opt-in real-Cine integration tests. No image exports.
  Local smoke testing reproduced 8146 vs approximately 4073.32 fps; the timing
  mismatch remains unresolved. See [Cine Reader usage and limitations](docs/cine_reader.md).
- Viewer UI v1 (feature branch, awaiting review): Graphics View canvas,
  asynchronous frame navigation, 64-frame LRU, review playback, metadata/TIME64,
  bookmarks, portable sessions and pixel-exact PNG export. Added Qt-free open
  taxonomy/annotation records, append-only prediction review, read-only
  point/bbox/polygon overlays and future tool/prediction-provider interfaces.
  Revalidated Cine Reader using VisionLab Python 3.12.10 before documenting
  this environment. Default labels are examples, not an exhaustive taxonomy.
- Windows desktop launch: a local shortcut can target VisionLab's `pythonw.exe`
  with `scripts/launch_viewer.py` as its argument and the repository as its
  working directory. This opens the viewer without a console; use File > Open
  Cine to select a recording. Machine-specific shortcut paths stay outside Git.
- Repository quick launch: added `launch_viewer.cmd` with portable interpreter
  discovery and an ignored local interpreter setting; clarified that the tested
  environment is not a permanent dependency lock. Anonymized the timing-policy
  test filename without changing its timing observations or scientific rules.

```console
python scripts/inspect_cine.py --input data/raw/example.cine --json outputs/inspect.json
python scripts/build_cine_inventory.py --root data/raw --csv outputs/inventory.csv --json outputs/inventory.json
```
