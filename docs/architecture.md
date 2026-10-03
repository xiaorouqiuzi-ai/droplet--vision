# Research architecture

Object segmentation and state analysis are separate contracts. Models are
selected by task/object; a physical state never requires its own YOLO model.

| Layer | Responsibility | Package |
| --- | --- | --- |
| 1 — Cine infrastructure | Decode frames, preserve metadata and raw TIME64 | cine |
| 2 — Preprocessing | Document ROI, transformations and intensity changes | preprocessing |
| 3 — Segmentation | Parent, cavity candidate, daughter and optional interference masks | segmentation |
| 4 — Tracking | Associate instances through time; record ambiguity and lineage | tracking |
| 5 — State/Event analysis | Infer provisional states/events from temporal evidence | states, events |
| 6 — Scientific metrics | Produce calibrated, uncertainty-aware measurements | metrics |
| 7 — Statistical outputs | Aggregate by experiment into datasets and figures | datasets |

These are responsibility layers, not a rigid one-pass execution order.
For example, YOLO-seg may supply parent, cavity and daughter masks. `metrics`
then derives area, perimeter, D_eq, circularity, cavity fraction and fragment
count. `states`/`events` consume those time series to assess NUCLEATION,
PUFFING and MICRO_EXPLOSION; event-conditioned metrics follow afterward.

Planned analyzers cover evaporation, nucleation, bubble growth, puffing,
micro-explosion and ignition. `states` describes intervals/frame states;
`events` records onsets, supporting evidence and uncertainty. No analyzer or
segmentation algorithm is implemented in this scaffold.

Do not create a giant `micro_explosion_yolo.py` combining segmentation,
event classification, measurement and plotting. Future state-specialized
models must still emit the same object-mask contract.

## Interfaces and provenance

`FrameResult` identifies a frame by `(cine_id, frame_index)` and carries optional
masks, state and timing provenance. `FrameMetrics` carries optional 2D values;
associate it with that frame key in downstream records. Missing measurements
are `None`; zero is reserved for an actual measurement.

Adapters must document mask representation, image dimensions, coordinate
origin, ROI/transform history, instance IDs, model IDs, calibration and
preprocessing provenance in metadata. Daughter/cavity instances must remain
distinguishable. The schema intentionally accepts backend-neutral mask types.
Raw TIME64 integers must survive every serialization boundary.

Chuzi-PY owns Cine/data processing; Torch-GPU owns future GPU inference and
training. Keep optional backend imports inside their adapters. Core schema,
enums and tests depend only on the standard library. Configuration and model
metadata bridge the environments without merging them.
