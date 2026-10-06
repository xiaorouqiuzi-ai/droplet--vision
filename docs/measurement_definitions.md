# Two-dimensional visual measurements

Status: **Planned measurement definitions**. The Viewer does not compute these
quantities. Derived results belong to the separate Measurement layer in the
[data architecture](data_architecture_concept_v1.md), not annotation geometry.

These are projected image measurements. `_area_px` fields store square pixels;
perimeter, equivalent diameter and shell proxy fields store pixels. Physical
unit conversion requires recorded pixel/mm calibration and its uncertainty.
Missing/invalid measurements are `None`, not zero.

| Quantity | Definition |
| --- | --- |
| Parent projected area A_p (A_parent) | Area enclosed by the parent projected outline, including internal cavity candidates |
| Parent perimeter P_p | External parent outline length; record contour estimator and smoothing |
| Equivalent diameter D_eq | 2 * sqrt(A_p / pi) |
| Circularity C | 4 * pi * A_p / P_p^2; undefined if P_p is zero |
| Internal cavity total area A_cavity,total | Union area of identified internal cavity masks inside the parent; no overlap double-counting |
| Cavity fraction phi_cavity | A_cavity,total / A_parent; undefined without positive parent area |
| Largest cavity area | Largest identifiable cavity instance projected area |
| Cavity count | Count of identifiable cavity instances |
| Minimum shell-thickness proxy | Minimum cavity-boundary to parent-external-interface distance in 2D |

The shell proxy is not a true 3D shell thickness. Without a cavity it is
undefined; a validated touching boundary can yield zero. Flag masks outside
the parent or ambiguously overlapping cavities for review before measurement.
Count zero only when a valid observation establishes absence; unresolved or
unobserved objects remain missing.

## Daughter measurements

Retain each daughter equivalent diameter, daughter count, mean diameter,
median diameter, size PDF and size CDF. Document sampling unit (frame, event,
or tracked unique droplet), field of view, censoring, histogram bins and
normalization so repeated tracks do not silently inflate pooled counts.

D32 = sum(d_i^3) / sum(d_i^2) is disabled until optical-resolution validation.
Any future use must state diameter definition and detection/censoring limits;
2D equivalent diameters do not establish true 3D droplet sizes.

Never label projected area as true three-dimensional surface area or volume.
If a later spherical assumption is justified, report **sphere-equivalent
volume** and **sphere-equivalent surface area**, explicitly as model-assumed
quantities rather than directly observed geometry.

## Internal optical features (reserved)

Future features include mean internal grayscale, grayscale standard deviation,
intensity histogram, local contrast, radial intensity profile, internal
gradient statistics and texture descriptors. Record ROI/mask, intensity scale,
exposure, illumination, normalization and preprocessing for reproducibility.

These may help study evaporation, nucleation, bubble growth, puffing precursors
and micro-explosion precursors. Grayscale feature ≠ physical phase identity.
Do not assign bright = bubble or dark = liquid. Human validation is required.

## Validation requirements

Assess pixel/mm calibration, minimum resolvable diameter, optical resolution,
depth of field and segmentation uncertainty before physical interpretation.
Compare IoU/Dice/mask quality alongside area, diameter, count and
cavity-fraction errors. YOLO confidence ≠ physical measurement confidence.
No calibration values, detection cutoffs or error tolerances are assumed here.
