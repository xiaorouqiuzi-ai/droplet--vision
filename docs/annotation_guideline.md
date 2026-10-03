# Annotation Guideline v0.1

## Spatial labels

| Label | Scope |
| --- | --- |
| parent_droplet | Identifiable primary suspended droplet outline |
| internal_cavity_candidate | Visually identifiable internal cavity-like region |
| daughter_droplet | Individually identifiable detached droplet instance |
| flame (optional, future) | Visible flame region |
| soot (optional, future) | Visible soot-like interference requiring validation |
| support_structure (optional, future) | Support wire or structure |
| uncertain_region (optional, future) | Ambiguous image region; future annotation extension |

`internal_cavity_candidate` does not mean a physically proven vapor bubble.
Backlit bright/dark structures are affected by refraction, droplet thickness,
focus, depth of field, illumination and motion blur. The model recognizes
visually identifiable internal cavity-like regions; scientific analysis owns
their physical interpretation.

Annotate visible boundaries and separate cavity/daughter instances. Record
occlusion, blur, overlap and unresolved boundaries rather than inventing hidden
geometry. The parent projected outline includes its internal candidate regions;
cavity masks are separate nested observations. Document uncertain membership
or boundary choices and seek author adjudication before ground-truth release.
Preserve frame/Cine identity, annotator, annotation version and review status.

## Temporal state labels

EVAPORATION, NUCLEATION, BUBBLE_GROWTH, PUFFING, MICRO_EXPLOSION, IGNITION,
POST_BREAKUP, UNCERTAIN.

State labels are not segmentation classes. They require temporal context and
the provisional event definitions. UNCERTAIN is explicitly permitted: never
force an annotator to guess. Missing/unreviewed state (`None`) differs from a
reviewed but ambiguous state (`UNCERTAIN`). `uncertain_region` is a future
spatial annotation extension, not currently an ObjectType enum member.

Where processes overlap, preserve supporting annotations and ambiguity in
metadata; the current single-state field is only a summary, not evidence that
the processes are mutually exclusive. Record onset uncertainty and original
timestamps; do not infer physical timing from nominal frame rate.
