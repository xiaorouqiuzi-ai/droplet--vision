# Practical annotation guidance

The [Droplet Vision labeling scheme v1.0](annotation_labeling_scheme_v1.md)
is the single source of truth for six Object IDs, ten multi-select Frame
State IDs, and the independent `uncertain` quality flag. This guide adds
practical advice; it does not maintain a second label registry.

## Visible evidence and boundaries

Annotate visible boundaries and separate cavity/daughter instances. Record
occlusion, blur, overlap and unresolved boundaries rather than inventing hidden
geometry. The parent projected outline includes its internal candidate regions;
cavity polygons are separate nested observations. Document uncertain membership
or boundary choices and seek author adjudication before ground-truth release.

`internal_cavity_candidate` does not mean a physically proven vapor bubble.
Backlit bright/dark structures can reflect refraction, droplet thickness, focus,
depth of field, illumination and motion blur. Spatial annotations describe
visible structures; scientific analysis owns physical interpretation.

Use an optional instance name to make crowded frames easier to review.
Preserve Cine/frame identity, annotation version and review provenance.
The [Editor guide](annotation_editor.md) explains drawing, correction,
confirmation, saving and immutable history.

## Frame-level judgments

Object annotations answer what is visible; Frame States describe what is
happening. Use adjacent frames for dynamic judgments such as cavity growth and
oscillation. States support multiple selections, subject to the approved
simple-evaporation exclusion rule. Do not infer onset from an isolated image.

Uncertainty is a quality flag, not a physical state or an object category.
An unannotated frame and a reviewed frame with uncertain evidence are different;
retain the record and explanatory notes rather than forcing a guess.

Ignition, auto-ignition and bursting are not v1.0 manual state labels.
[Provisional event definitions](event_definitions.md) describe future analysis,
not extra UI labels. Scientific time comes from TIME64 with retained timing
status, never nominal frame rate.

## Review and consistency

1. Inspect raw and display-enhanced views without changing raw-coordinate geometry.
2. Confirm drafts deliberately; a closed polygon is still a draft.
3. Save the AnnotationDocument separately from ViewerSession.
4. Use [portable review packages](portable_review_package.md) for external review.
   Preserve original records and inspect returned candidates before adoption.
5. Keep raw pixels as the scientific intensity source. Display style, daughter
   numbers and Ref90 gain are not physical evidence or Ground Truth geometry.

See the [documentation index](README.md) for workflow and architecture references.
