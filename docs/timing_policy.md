# Timing policy

For the reported test Cine `32BD8E12-500c.cine`:

| Source | Reported observation |
| --- | --- |
| SETUP FrameRate | 8146 fps |
| dFrameRate | 8146.0 |
| fDecimation | 1.0 |
| Frame TIME64 timestamps | Average approximately 4073.32 fps |
| Current status | TIMING_MISMATCH_UNRESOLVED |

These are supplied experimental observations, not a new validation performed
by this scaffold. The discrepancy is unresolved; do not infer its cause.

Do not formally compute t_nuc, t_puff, t_ME, t_ign or t_life using
`frame_index / nominal_fps`. Prefer elapsed time:

```text
delta_t_s = (TIME64_i - TIME64_reference) / 2^32
```

Subtract raw integers before conversion to float to retain precision. Preserve
raw TIME64 values, frame indices, reference origin, timestamp ordering and any
missing-frame information. Non-monotonic or missing timestamps require review,
not a silent fallback to nominal fps.

Retain `fps_header`, `fps_timestamp`, `fps_ratio` and `timing_status`.
Define fps_ratio = fps_header / fps_timestamp; document the time interval and
estimator used for fps_timestamp. For a contiguous valid sequence an average
rate can be computed from frame intervals / elapsed timestamp time. Do not
confuse exported subsampling with the original acquisition interval.

All absolute times remain provisional until the mismatch is explained.
Timestamp-derived elapsed event times must also carry the unresolved status.
Only documented validation can promote a record to TIMING_VALIDATED or
TIMING_VALIDATED_WITH_DECIMATION; absent evidence is TIMING_UNKNOWN.

Normalized lifetime timing may be retained:

```text
tau_event = (t_event - t_start) / (t_life - t_start)
```

Here t_life denotes the lifetime endpoint timestamp, not an elapsed duration.
Document start and endpoint criteria, require a positive denominator, retain
the original timestamps, and propagate provisional timing status. Normalizing
does not resolve irregular timestamps or establish timing validity.
