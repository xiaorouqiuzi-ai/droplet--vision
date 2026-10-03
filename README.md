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
| 1 | Cine infrastructure | Active |
| 2 | Classical CV baseline | Planned |
| 3 | AI segmentation | Planned |
| 4 | Scientific measurement and event analysis | Planned |

## Organization

`src/droplet_vision` holds reusable interfaces and future processing modules;
`configs` holds portable examples; `docs` holds scientific policies; `tests`
holds small standard-library tests. `data`, `models`, `training`, `outputs`,
`notebooks`, and `scripts` document their intended roles.

Start with [architecture](docs/architecture.md), [model strategy](docs/model_strategy.md),
[annotation guidance](docs/annotation_guideline.md), and [timing policy](docs/timing_policy.md).

## Environments and checks

Keep Chuzi-PY (Cine reading, metadata, frame extraction, traditional CV,
measurement, dataset preparation) separate from Torch-GPU (future PyTorch,
CUDA, YOLO/U-Net training and inference). Exchange stable masks, metadata, and
measurement records rather than importing GPU frameworks into Cine modules.

The reported Chuzi-PY baseline is Python 3.9.13, NumPy 2.0.2, Pillow 11.3.0,
PIMS 0.7, imageio 2.37.2, Slicerator 1.1.0, and tifffile 2024.8.30.
These are environment observations, not required package dependencies.
This scaffold requires only Python >=3.9; no installation is needed for checks.
From the repository root, using the existing Chuzi-PY interpreter:

```console
python -m unittest discover -s tests -v
python -m compileall src
```

Local paths belong in ignored local configuration, never machine-specific
versioned settings. Raw Cine files, exported datasets, and weights stay outside
Git; see [data policy](docs/data_policy.md).
