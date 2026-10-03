# Model strategy

Models follow objects/tasks; analyzers follow physical processes.

| Family | Task | Initial strategy |
| --- | --- | --- |
| A | Parent droplet segmentation | Traditional CV baseline first; deep learning only when validated CV fails |
| B | Internal cavity / bubble candidate segmentation | Compare YOLO instance segmentation and U-Net/semantic segmentation against human ground truth |
| C | Daughter-droplet instance segmentation | Prefer YOLO instance segmentation for independent instance masks, counts and size distributions |
| D | Optional interference segmentation | Future flame, soot, support wire/structure and optical artifacts |

Semantic cavity masks require a documented instance-separation method before
reporting cavity counts. No architecture is claimed trained or validated here.

A future specialized model such as `daughter_seg_micro_explosion_v001` is
allowed only after benchmarks demonstrate a shared model is insufficient.
Do not preemptively create a YOLO model for each state. Specialized adapters
must preserve the shared measurement interface.

## Model registry contract

Each future registry entry must provide these keys:

| Key | Meaning |
| --- | --- |
| model_id | Stable unique model identifier |
| task | Segmentation task, e.g. instance_segmentation |
| object_type | Spatial object label from the object vocabulary |
| applicable_states | List of supported DropletState names; not event predictions |
| architecture | Actual model architecture or classical method |
| dataset_version | Versioned training/validation dataset reference |
| training_run | Training provenance; null for untrained/classical entries |
| weights_path | Local/external artifact reference; may be null |
| git_commit | Source revision used for the run |
| validation_metrics | Measured results and benchmark identity; empty until evaluated |

Examples are proposals, not registry entries for existing models. Never invent
weights, run identifiers, validation numbers or scientific thresholds.

## Dataset separation

Adjacent high-speed frames are highly correlated. Frame-level random
train/validation/test splits are prohibited. Prefer splitting by Cine /
experimental run, keeping linked runs together; otherwise split by experimental
replicate / condition block. Exceptional within-Cine temporal splits require a
large temporal buffer with a documented justification and leakage assessment.
Do not select a numerical buffer without experimental evidence.

Maintain an independent hard-case holdout set covering motion blur, dense
fragmentation, overlapping daughters, support interference and flame/soot
interference. Do not use the holdout for tuning. Record split membership and
dataset versions, and fit preprocessing only on training data.

## Scientific validation

YOLO confidence is not physical measurement confidence. Validation must
include IoU, Dice / mask quality and physical measurement errors: area,
diameter, count and cavity fraction, compared with human ground truth.
Assess pixel/mm calibration, minimum resolvable diameter, optical resolution,
depth of field and segmentation uncertainty. Their values remain unassigned
until measured. Report performance by condition and hard-case category.
