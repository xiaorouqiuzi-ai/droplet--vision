<div align="center">
  <img src="src/droplet_vision/ui/assets/icons/planico.png" alt="Droplet Vision" width="200">

# Droplet Vision

**High-Speed Droplet Annotation, Collaboration, and AI-Assisted Quantification Workstation**

A research-oriented desktop workstation for Phantom Cine review, reproducible annotation,
portable collaboration, and future AI-assisted transient droplet analysis.

English | [简体中文](README.zh-CN.md)

[![Project: Research Software](https://img.shields.io/badge/project-research%20software-3B6FB6)](#overview)
[![Workflow: Human-in-the-loop](https://img.shields.io/badge/workflow-human--in--the--loop-2A9D8F)](#core-workflows)
[![Data: Phantom Cine](https://img.shields.io/badge/data-Phantom%20Cine-E9A23B)](docs/cine_viewer.md)
[![UI: PySide6](https://img.shields.io/badge/UI-PySide6-7A6FAC)](pyproject.toml)
<br>
[![Python: 3.12 tested](https://img.shields.io/badge/Python-3.12%20tested-3B6FB6)](#installation)
[![Platform: Windows](https://img.shields.io/badge/platform-Windows-7B8794)](docs/getting_started.md)
[![License: BSD-3-Clause](https://img.shields.io/badge/license-BSD--3--Clause-D96C75)](LICENSE)
[![Status: Active Development](https://img.shields.io/badge/status-active%20development-2A9D8F)](#roadmap)

</div>

## Overview

High-speed droplet experiments produce more frames than researchers can inspect or
label exhaustively. Droplet Vision connects read-only Phantom `.cine` access with
traceable human annotation, temporal-state review, and portable collaboration.

The current workstation supports manual and grayscale-assisted annotation. Its
longer-term direction is AI-assisted quantification: **trained models, automatic
physical-event detection, and scientific measurement pipelines are not supplied**.
A model is one future component of an evidence-and-review workflow.

## Interface

<div align="center">
  <a href="Example/236.png"><img src="Example/236.png" alt="Droplet Vision annotation workspace and About dialog" width="95%"></a>
</div>

*Cine metadata, object overlays, frame states, timeline navigation, and offline
collaboration in one workspace. This original screenshot shows the earlier
Portable Review Mode, now named Annotation Package Mode; some controls have evolved.*

Data, Scheme, and current annotations sit on the **left**; the image is in the
**center**; annotation tools and states sit on the **right**. The bottom bar handles
navigation and review speed. Chinese and English UI text switches live.

## Highlights

| Area | Available in the current source |
| --- | --- |
| Cine review | Lazy frame access, bounded raw cache, full TIME64, timing diagnostics, zoom/pan and Auto Fit |
| Display | Raw, Cine-locked Photometric Normalization (Ref90), Manual and Auto; raw PNG export |
| Object annotation | Polygon, Point, raw-grayscale Magic Wand, editable closed drafts, Space confirmation, vertex/midpoint editing and Undo/Redo |
| Annotation context | Optional instance names, Scheme-driven labels/colors, daughter numbering, multi-label Frame State, separate Uncertain and Notes |
| Navigation and tasks | Clickable human-annotation markers, resumable Annotation Queue, deterministic anchor/change sampling and separate uniform sampling |
| Annotation Packages | Raw-only or annotated `.dvapkg`, offline editing, legacy `.dvrpkg` loading, atomic Quick Save and Save As |
| Collaboration | Immutable history, returned Reviewed candidates, provenance and base/local/reviewer conflict choices |
| Reusable rods | Cine-wide or package-wide support-rod templates, sparse per-frame translation and local geometry overrides |
| Batch generation | Recursive Cine discovery, mirrored folders, one package per Cine, progress/cancel and skip-existing resume |

## Quick Start

In Windows PowerShell, with Python 3.12 available:

```powershell
git clone https://github.com/xiaorouqiuzi-ai/droplet--vision.git
cd droplet--vision
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[cine,ui]"
python scripts/launch_viewer.py
```

Choose **File → Open Cine…** or **Functions → Open Annotation Package…**.
An annotation package needs no original Cine. Follow [Getting Started](docs/getting_started.md)
for environment setup, the first annotation, and saving/reopening work.

## Installation

Use a **source checkout** with its `configs/` directory. The package declares
Python `>=3.9`; the tested Windows desktop environment uses **Python 3.12.10**.
That metadata minimum does not imply that all optional UI dependencies support
or have been tested on every Python version.

[pyproject.toml](pyproject.toml) defines `cine` (PIMS 0.7) and `ui` (PySide6 6.10.2).
The base interfaces have no mandatory dependencies. Implemented workflows need
no GPU, Torch, YOLO, OpenCV or SciPy.

After activation, `launch_viewer.cmd` is the Windows launcher. For a desktop
shortcut or an external environment, see [launcher setup](docs/getting_started.md#launch).
Machine-specific interpreter paths belong in local settings, not versioned files.
Windows installer packaging and file association remain planned.

## Core Workflows

```text
A · Local annotation
Cine → Frame review → Object annotation + Frame States → AnnotationDocument

B · Offline collaboration
Cine dataset → Uniform / batch sampling → .dvapkg → Collaborator
             → Annotation or review → Returned package → Reviewed candidates

C · Future analysis
Ground Truth → Model training → Prediction → Human review → Measurement
```

For annotation, apply a Scheme, select an unlocked drawing layer and an object,
then draw and close the draft. With canvas focus, **Space confirms a closed
Polygon or Magic Wand draft**; **Esc cancels**. Space on an open draft neither
confirms nor starts playback. Without a draft it toggles Review Playback; text
inputs retain normal spaces. Enter remains supported.

Save the **AnnotationDocument** explicitly. ViewerSession stores navigation and
UI state separately. See [tools and shortcuts](docs/annotation_editor.md#keyboard-shortcuts).

## Annotation Model

Two annotation layers answer different questions, with an independent quality flag:

| Content | Meaning |
| --- | --- |
| Object annotations | “What is visible, and where?” — six v1 stable IDs, raw-coordinate geometry |
| Frame States | “What is happening in this frame?” — ten v1 stable IDs, multi-label judgments |
| Quality | `uncertain` and notes describe evidence limitations, not physical phenomena |

`internal_cavity_candidate` describes visible internal structure without asserting
bubble identity. Dynamic states need neighboring-frame evidence. Magic Wand and
change-peak sampling do not classify physical events.
The [Labeling Scheme v1.0](docs/annotation_labeling_scheme_v1.md) is the single
source of scientific definitions; display translations never rename stable IDs.

## Annotation Packages

**`.dvapkg` is a portable annotation task and collaboration format.** It contains
selected raw PNG frames, TIME64 and timing status, an Annotation Scheme snapshot,
optional objects/Frame States, Ref90 provenance, review history and SHA-256 checksums.
Zero existing annotations is valid. Older `.dvrpkg` files remain readable.

A collaborator can annotate or review a `.dvapkg` without receiving multi-gigabyte
or multi-terabyte source Cine datasets. Package size depends on its contents.

- **Create:** Functions → Create Annotation Package from Uniform Cine Sampling…
  creates exactly N unique targets when the Cine has at least N frames, including
  the first and last. With 32196 frames and N=50: 50 points, 49 intervals.
- **Work offline:** Open the package, annotate, and use the bottom-right **Save
  Annotation Package** button when dirty. It atomically overwrites the current
  `.dvapkg`; **Save As** retains a separate version or return copy.
- **Reuse rods:** Apply to entire package affects only included target/context
  frames; Apply to entire Cine belongs to Cine mode. Both support sparse offsets.
- **Return:** Import adds Reviewed candidates and preserves conflicts/provenance;
  it never silently replaces canonical human Ground Truth or the Cine template.

Full instructions and candidate-adoption limits: [Annotation Package](docs/annotation_package.md).

## Batch Package Generation

**Functions → Create Annotation Packages from Folder…** recursively samples each
Cine and preserves the source folder name and subdirectories:

```text
Source                       Output
A/                           Packages/
├── B/111.cine                └── A/
└── C/222.cine                    ├── B/111.dvapkg
                                 └── C/222.dvapkg
```

Defaults: **20 targets per Cine**, **0 context frames**, **Skip existing**.
Short Cine files export all available frames. Each source is opened in turn;
completed packages survive cancellation, and one failed Cine does not stop the rest.
The source tree is read-only. `_batch_manifest.json` records relative paths,
counts and outcomes; rerunning with Skip existing provides simple resume.
See [batch details](docs/annotation_package.md#batch-annotation-package-generation).

## Data & Scientific Integrity

- **Raw Cine is read-only.** Display transformations do not change scientific pixels.
- **Ref90 does not replace raw intensity.** Raw export and Magic Wand use raw pixels.
- **Geometry uses raw image coordinates**, independent of zoom, pan and display mode.
- **TIME64 is the scientific timing source.** Preserve timing status; never substitute
  `frame_index / header_fps` for scientific time or dismiss an unresolved mismatch.
- **Review Speed is UI-only:** 1000 frames/s advances approximately 1000 source
  frames per real second, potentially skipping displayed images. It is not acquisition FPS.
- **Ground Truth ≠ Prediction ≠ Measurement.** Predictions must not overwrite human
  Ground Truth. Packages transport work; they are not another canonical data layer.
- Future training/evaluation splits must be by **Cine / experiment run**, not random
  sampled frames, to limit leakage between correlated images.

See [data architecture](docs/data_architecture_concept_v1.md) and
[preprocessing policy](docs/image_preprocessing_policy.md).

## AI Integration Status

The repository is **AI-ready at the architecture level**: prediction-provider/layer
interfaces, immutable derivatives and review provenance provide extension points.
Production model import/inference, dataset export, segmentation baselines, tracking,
automatic measurements and temporal event inference are **future work**.
No trained weights or automatic micro-explosion detection are provided.

## Repository Structure

```text
droplet--vision/
├── configs/                 Annotation Schemes, sampling and display presets
├── docs/                    Guides, scientific policies and architecture
├── Example/236.png          Original workspace screenshot
├── scripts/                 Launcher, inventory, queue and documentation tools
├── src/droplet_vision/
│   ├── cine/                Read-only frame and timing access
│   ├── annotations/         Documents, Schemes and annotation assistance
│   ├── sampling/            Uniform / heuristic sampling and queues
│   ├── review_package/      Annotation Package export, batch and merge
│   └── ui/                  Workstation; assets/icons/ contains PNG and ICO
├── tests/                   Synthetic, Qt and opt-in real-Cine tests
├── launch_viewer.cmd
├── README.md / README.zh-CN.md
└── LICENSE
```

## Documentation

Start with the [Documentation Index](docs/README.md).

| Document | Purpose |
| --- | --- |
| [Getting Started](docs/getting_started.md) | Installation, launch and first workflows |
| [Cine Viewer](docs/cine_viewer.md) | Navigation, review speed, metadata and display |
| [Annotation Editor](docs/annotation_editor.md) | Tools, drafts, shortcuts and support-rod templates |
| [Labeling Scheme v1](docs/annotation_labeling_scheme_v1.md) | Authoritative object, state and quality definitions |
| [Annotation Package](docs/annotation_package.md) | Offline tasks, batch generation, review and conflicts |
| [Frame Sampling & Queue](docs/frame_sampling_queue.md) | Reproducible candidate selection and resumable work |
| [Data Architecture](docs/data_architecture_concept_v1.md) | Ground Truth / Prediction / Measurement boundaries |
| [Preprocessing Policy](docs/image_preprocessing_policy.md) | Raw, display and model preprocessing separation |
| [Photometric Presets](docs/photometric_presets.md) | Frozen Ref90 settings and provenance |
| [Annotation Architecture](docs/annotation_architecture.md) | Record history, persistence and developer contracts |

## Validation

From the activated environment at repository root:

```powershell
python -m pip check
$env:QT_QPA_PLATFORM = "offscreen"
python -m unittest discover -s tests -v
python -m compileall src scripts
python scripts/check_docs_links.py
git diff --check
```

The suite covers Cine I/O, raw pixels/timing, annotation editing, Frame States,
packages/merging, sampling and Qt UI behavior. Real-Cine integration paths are
opt-in through `DROPLET_VISION_TEST_CINE` and `DROPLET_VISION_LAYOUT_TEST_CINE`;
skipped tests are not evidence of real-data validation. Remove `QT_QPA_PLATFORM`
from the environment before launching the normal desktop UI.

## Known Limitations

- Cine validation primarily covers available monochrome Phantom variants.
- TIME64 status and unresolved timing mismatches require experimental review.
- Magic Wand and package export currently require uint8 grayscale; Wand rejects
  holes/degenerate contours and offers no mask-brush editor.
- A package contains only its included frames, not the rest of the original Cine.
- Returned Frame State and package-template candidates are retained, but dedicated
  comparison/adoption UI is not yet implemented.
- Checksums detect corruption, not reviewer identity; collaboration is offline,
  not real-time synchronization. Runtime configs still assume a source checkout.

## Roadmap

Planned, without release-date commitments:

- Windows packaged release/installer and `.dvapkg` file association.
- Dataset export and prediction import/provider integration.
- Segmentation baselines, measurement extraction and TIME64-based temporal event logic.

## Contributors

<div align="center">
  <a href="https://github.com/xiaorouqiuzi-ai">
    <img src="https://github.com/xiaorouqiuzi-ai.png?size=120" width="84" alt="xiaorouqiuzi-ai">
    <br>
    <sub><b>@xiaorouqiuzi-ai</b></sub>
  </a>
  <br>
  Repository Owner
  <br><br>
  <a href="https://github.com/BrunelXian">
    <img src="https://github.com/BrunelXian.png?size=120" width="84" alt="BrunelXian">
    <br>
    <sub><b>@BrunelXian</b></sub>
  </a>
  <br>
  Collaborator
</div>

The desktop UI is named **Droplet Annotation Workstation**, within the Droplet Vision project.
[Repository on GitHub](https://github.com/xiaorouqiuzi-ai/droplet--vision).

## License

Droplet Vision source code is licensed under [BSD-3-Clause](LICENSE).
Third-party libraries and future model runtimes retain their own licenses.
Users distributing packaged binaries should review the licenses of bundled
third-party dependencies; this project does not relicense them.
