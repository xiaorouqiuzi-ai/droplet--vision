# Data and provenance policy

Never commit `.cine`, `.chd`, raw videos, bulk frame exports, YOLO datasets,
model weights or large prediction outputs. Store them externally or in ignored
local data directories. Git stores source, configuration examples, Markdown
documentation and tiny test fixtures only. Do not modify raw Cine files.

`data/raw`, `data/frames`, `data/processed`, `data/annotations`, `data/datasets`,
`outputs`, and training runs are ignored for local products. README exceptions
retain documentation. Weight/video patterns also apply outside these folders;
ignore rules are a guardrail, not permission to force-add prohibited assets.
Docs, configs, src and tests remain versioned.

Use portable relative-path examples and ignored `*.local.*` configurations for
machine-specific paths. Never commit absolute Windows paths or credentials.
The application configuration loader is future work; examples specify intent.

Future dataset manifests should retain Cine/run/replicate identity, provenance,
calibration version, annotation version, split membership, raw timestamps and
timing status without embedding large data. Model registries reference external
weights; no weights are supplied at this stage. Review `git status` and staged
file sizes before every commit; never force-add generated data.
