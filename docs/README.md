# Droplet Vision Documentation

**Implemented** means available in source; **Experimental** means an assistance
method with limited validated scope; **Planned** means a contract or research
direction without an executable workflow.

## Documentation Map

- **New user:** [Overview](../README.md) → [Getting Started](getting_started.md) → [Annotation Editor](annotation_editor.md).
- **Reviewer:** [Overview](../README.md) → [Portable Review Package](portable_review_package.md).
- **Developer:** [Annotation Architecture](annotation_architecture.md) → [Data Architecture](data_architecture_concept_v1.md).
- **Research definition:** [Labeling Scheme](annotation_labeling_scheme_v1.md) → [Preprocessing Policy](image_preprocessing_policy.md) → [Timing Policy](timing_policy.md).

## Getting Started

| Guide | Purpose |
| --- | --- |
| [Getting Started](getting_started.md) | Install, launch, save and reopen a first annotation |
| [Cine Viewer](cine_viewer.md) | Navigation, playback, display and raw export |
| [Cine Reader](cine_reader.md) | Read-only Python/CLI access and format limits |

## Annotation

| Guide | Responsibility |
| --- | --- |
| [Annotation Editor](annotation_editor.md) | Tools, drafts, State/quality and persistence |
| [Labeling Scheme v1.0](annotation_labeling_scheme_v1.md) | **Single source of truth for scientific annotation semantics** |
| [Sampling and Queue](frame_sampling_queue.md) | Reproducible selection and resumable manual progress |
| [Annotation guidance](annotation_guideline.md) | Boundary uncertainty and review practice, not a separate registry |

## Collaboration

[Portable Review Package](portable_review_package.md) covers annotator/reviewer
roles, checksums, returned candidates and conflicts. This is an implemented
offline workflow, not cloud sync or automatic Ground Truth approval.

## Data Architecture

[Data Architecture](data_architecture_concept_v1.md) is the **single source of
truth for Ground Truth / Prediction / Measurement organization**. Proposed
Prediction and Measurement stores are not implemented production stores.
[Research architecture](architecture.md) maps modules and planned analysis stages.

## Scientific Policy

- [Timing and TIME64](timing_policy.md): experimental timing uncertainty.
- [Image preprocessing](image_preprocessing_policy.md): display/model/science separation.
- [Photometric presets](photometric_presets.md): Ref90 candidate, not universal calibration.
- [Data policy](data_policy.md): source protection and portable references.
- [Measurement definitions](measurement_definitions.md): proposed quantities, not delivered results.
- [Event definitions](event_definitions.md): future onset analysis, separate from manual State.

## Developer Reference

- [Annotation Architecture](annotation_architecture.md): records, active pointers, atomic save, lineage.
- [Model strategy](model_strategy.md): future interfaces, leakage controls and validation.
- [Scripts](../scripts/README.md): command-line entry points.
- [Validation](../README.md#validation): tests and local Markdown link checks.

Tutorials link to scientific specifications instead of duplicating full definitions.
