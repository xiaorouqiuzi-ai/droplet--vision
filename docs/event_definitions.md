# Provisional event definitions

**PROVISIONAL — requires final experimental-author validation.**

Status: **Planned event-analysis definitions**, not implemented event detection.
These onset concepts are not additional manual Frame State IDs. The approved
[labeling scheme](annotation_labeling_scheme_v1.md) is the sole v1.0 label
registry; ignition onset is explicitly excluded from it.

All definitions below carry this status; no numerical thresholds are fixed.

| Event | Provisional definition |
| --- | --- |
| NUCLEATION | First clearly identifiable internal cavity/bubble-like structure; a visual onset, not proof of vapor phase |
| PUFFING | Localized interface rupture associated with limited ejection, while the parent droplet largely remains identifiable |
| MICRO_EXPLOSION | Rapid catastrophic fragmentation of the parent droplet into multiple daughter droplets |
| IGNITION | First appearance of persistent visible flame; persistence criterion TBD |

Use time-series evidence, retain frame indices/raw timestamps and record
uncertain onset intervals. Event thresholds, persistence rules and the
start/lifetime endpoint conventions require experimental-author validation.
Use the independent `uncertain` quality flag and notes when evidence does not
distinguish phenomena; do not introduce an UNCERTAIN physical state. Neither model class
nor confidence alone establishes a physical event.

Scientific event times must come from TIME64, retaining its timing status;
frame index divided by header FPS is not a scientific timing substitute.
