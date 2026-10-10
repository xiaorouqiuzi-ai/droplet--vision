# Droplet Vision @VERSION@

First public beta candidate. This release remains a draft until maintainer review.

## Highlights

- Phantom Cine reading and TIME64-aware frame review; Ref90 display normalization.
- Polygon, grayscale Magic Wand and Point annotations, editable drafts and Space confirmation.
- Frame States, quality flags and notes; bilingual UI and versioned Annotation Schemes.
- Annotation Packages for offline annotation and review without the original Cine.
- Uniform frame sampling and recursive batch generation with mirrored folder structure.
- Cine/package support-rod templates with sparse frame translation overrides.
- Timeline marker navigation, review provenance and conflict-aware returned-package import.

## Windows distributions

- Portable ZIP: extract the complete directory and run `DropletVision.exe`.
- Installer (when attached): installs shortcuts and package file types; Cine association is optional.
- No separate Python installation is required. Verify downloads against `SHA256SUMS.txt`.
- Existing `.dvrpkg` packages remain supported.

## Scientific integrity

Cine files remain read-only. Geometry uses raw image coordinates; TIME64 supplies
scientific timing. Display preprocessing, including Ref90, does not replace raw
pixels. Ground Truth, Prediction and Measurement remain separate layers.

## Beta status and planned work

Research software; validate results for your experiment. Binaries are unsigned.
Model integration, dataset export, automated measurement and temporal event logic
remain future work. Packaged frames do not provide access to missing Cine frames.
Third-party libraries retain their own licenses; the project source is BSD-3-Clause.
