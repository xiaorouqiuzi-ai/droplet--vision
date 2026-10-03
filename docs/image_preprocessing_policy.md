# Image preprocessing policy

**DISPLAY TRANSFORM ≠ SCIENTIFIC PIXEL DATA**

Display enhancement MUST NOT be interpreted as physical intensity correction.
Three separate pipelines must remain explicit:

1. **Display pipeline:** raw Cine frame → independent display copy → brightness,
   contrast, gamma or percentile stretch → QImage/canvas → human observation.
   This helps review and annotation only. It never modifies Cine files,
   CineReader output or the raw frame cache. Display settings are optional
   ViewerSession UI state, not scientific metadata or training configuration.
2. **Model preprocessing pipeline (future):** raw source → explicitly defined,
   fixed, reproducible and versioned preprocessing → YOLO/U-Net input. Record
   backend/version, parameters and source provenance. Viewer settings MUST NOT
   silently become training or dataset-export preprocessing, even if an annotator
   used gamma 0.6 or contrast 1.8 while reviewing an image.
3. **Scientific intensity pipeline:** raw pixels → explicitly documented
   scientific grayscale analysis. UI brightness/gamma/auto-stretch results are
   forbidden as a replacement source. Any future scientific calibration or
   correction requires separate validation, provenance and retained raw data.

Annotation geometry always uses original image pixel coordinates: origin at
top-left, x = column, y = row. Zoom, pan and display mode change only presentation.
Annotation JSON geometry must never depend on widget coordinates or enhancement
parameters. Review provenance may optionally record the display mode used, but
the geometry remains interpretable without it.

Export Current Frame means pixel-preserving **raw** PNG export. An enhanced
preview exporter, if added later, must be separately named and clearly marked
as unsuitable for scientific raw-data export. It is not implemented here.

Visible bright/dark regions are observations, not inferred phase identities.
Display operations do not identify bubbles, liquid, puffing or micro-explosion.
They do not change TIME64 timing policy or resolve timing mismatch.

CLAHE / local contrast enhancement may be added later as reproducible display
or preprocessing backends with the pipeline role explicitly recorded. No such
backend or new dependency is introduced by the current display update.
