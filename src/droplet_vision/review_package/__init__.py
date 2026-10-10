"""Portable review transport. Not a canonical annotation or measurement store."""
from .bundle import ReviewPackage, ReviewFrameProvider, export_package, context_frames
from .merge import merge_review, review_decision

# Public v2 names; retain the original API for existing callers and .dvrpkg tools.
AnnotationPackage = ReviewPackage
AnnotationFrameProvider = ReviewFrameProvider

__all__ = ['AnnotationPackage', 'AnnotationFrameProvider', 'ReviewPackage', 'ReviewFrameProvider', 'export_package', 'context_frames',
           'merge_review', 'review_decision']
