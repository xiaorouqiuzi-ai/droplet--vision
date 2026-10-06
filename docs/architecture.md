# Software architecture overview

This page maps implementation responsibilities. The normative storage and
provenance boundaries are defined in
[Data Architecture v1.0](data_architecture_concept_v1.md); object/state semantics
are defined in the [labeling scheme](annotation_labeling_scheme_v1.md).

## Current components

| Component | Responsibility | Status |
| --- | --- | --- |
| `cine` | Read-only Cine decoding, metadata and raw TIME64 | Implemented |
| `display` | Independent Raw/Manual/Auto/Ref90 display arrays | Implemented |
| `annotations` | Open labels, validated geometry, immutable records, active views, Frame States and Scheme metadata | Implemented |
| `sampling` | Anchors, raw-image change peaks, resumable JSON queues | Implemented |
| `review_package` | Sparse raw PNG packages, provenance and conflict-aware return import | Implemented v1; single-user workflow |
| `ui` | Viewer, annotation editor, queue and offline review interaction | Implemented; PySide6 optional |

CineReader returns raw pixels. The UI transforms a separate display array,
while geometry always uses raw image coordinates. Sampling ranks raw frame
differences. Annotation and review history never become source-video metadata.

The Qt-free AnnotationDocument owns records and active IDs. ViewerSession owns
UI state. The queue owns work-item status. A review package carries selected
frames and snapshots; it is not a replacement for the full source Cine or a
shared annotation database. See [Annotation architecture](annotation_architecture.md)
for persistence and command contracts.

## Future responsibilities

| Layer | Planned responsibility |
| --- | --- |
| Model preprocessing | Explicitly versioned dataset/model transformations |
| Segmentation | Backend-neutral object masks with model/run provenance |
| Tracking | Temporal association, ambiguity and lineage |
| State/event analysis | Contextual probabilities and onset evidence |
| Measurement | Calibrated projected metrics and uncertainty |
| Dataset/statistical output | Reproducible splits, exports and scientific figures |

Existing scaffolds/interfaces do not imply an implemented segmentation,
tracking, measurement or training pipeline. `inference.PredictionProvider`
is a future adapter interface. Prediction Store and Measurement Store remain
planned, separate from Human Ground Truth.

Object segmentation and state analysis are separate contracts. A physical
state does not require its own YOLO model. A future segmentation backend may
provide parent, cavity and daughter masks; measurement and temporal analysis
then consume those outputs with their own provenance. Do not combine all
responsibilities into one event-specific model module.

## Interfaces and dependencies

`FrameResult` identifies a frame by Cine/frame index and carries timing
provenance. Existing optional result/metric schema fields are extension points,
not evidence of computed measurements. Missing measurements are `None`;
zero is reserved for an actual measurement.

Adapters must document mask representation, dimensions, origin, ROI/transform
history, instance IDs, model ID and calibration. Raw TIME64 integers must
survive serialization. Optional backend imports belong inside their adapters.

The Viewer environment currently uses NumPy, Pillow, PIMS and PySide6.
Future GPU training/inference environments remain separate. No Torch,
Ultralytics or OpenCV dependency is required by the current workstation.

For usage start with [Getting Started](getting_started.md); for developer
details see [Annotation architecture](annotation_architecture.md),
[preprocessing policy](image_preprocessing_policy.md) and
[model strategy](model_strategy.md).
