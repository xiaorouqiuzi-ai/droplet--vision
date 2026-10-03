# Photometric preprocessing presets

## photometric_ref90_v1

The user-selected brightness reference is
`DBD__202012__2.0ulBD46450c8__frame_000966.png`.
Its whole-image raw P90 is **232**; the target is **90%**, or **208.8**.
The reference filename and actual SHA-256 are recorded in
[`photometric_ref90_v1.json`](../configs/photometry/photometric_ref90_v1.json).
The reference PNG remains external data and is not committed.

This gain-only preset was **accepted after visual review of 211 extracted
early frames**. It is an annotation / model preprocessing candidate, not final
YOLO preprocessing or a scientific grayscale measurement method.

For raw uint8 grayscale input, compute whole-image P90 using NumPy's linear
percentile method, then divide the target by that statistic. Clamp the gain to
the preset's fixed bounds, multiply in float64, round to nearest with ties to
even, clip to the uint8 range and convert to uint8. A nonpositive input P90
requires a raw copy and `INVALID_REFERENCE_STATISTIC`. No offset, gamma,
contrast stretch or denoising is included.

- Raw Cine and raw extracted PNGs remain unchanged.
- Normalized image geometry is identical to raw image geometry.
- Scientific grayscale measurements must continue to use raw pixels.
- Preview validation records describe only the current 211-image dataset;
  reaching its P90 target does not guarantee uniform visual backgrounds or
  future performance. High gain and saturation warnings remain relevant.

The JSON preset is the **single source of truth**. The Viewer now reads it for
default Cine-locked Ref90 display, estimating one gain from the 3% reference
frame; see [Viewer behavior](cine_viewer.md#photometric-ref90-default-cine-locked-display).
Future dataset exporter, YOLO and U-Net integrations that explicitly opt into this candidate
must load it, rather than hardcode its reference statistic, target fraction,
target intensity or gain bounds in Python. The current integration is display
only; it does not implement a dataset normalization backend or enable training
preprocessing. Raw export continues to preserve raw scientific pixels.

Changing the reference, target fraction, metric or gain rules requires a new
**v2 preset**. Do not silently alter v1 or recompute its accepted gain bounds
for a different dataset. Outputs should retain the preset ID and version as
provenance.
