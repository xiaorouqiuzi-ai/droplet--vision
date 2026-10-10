"""Explicit review decisions and non-destructive, per-record three-way import."""
from copy import deepcopy
from dataclasses import replace
from uuid import uuid4

from ..annotations import AnnotationDocument, AnnotationRecord
from ..annotations.schema import _now


def review_decision(package, cine_id, kind, record_id, status):
    if status not in ('accepted', 'rejected', 'needs_review') or kind not in ('object', 'state'):
        raise ValueError('Unsupported review decision')
    doc = package.documents[cine_id]
    package.mark_in_review()
    if kind == 'object':
        original = doc.records.get(record_id)
        derived = doc.derive(record_id, review_status='unreviewed' if status == 'needs_review' else status,
                             reviewer=package.provenance()['reviewer'])
        derived.attributes.update(package.provenance())
        derived.attributes['review_decision'] = status
        doc.add_record(derived, 'reviewed', activate=status != 'rejected')
        doc.transition(deactivate=[record_id])
        new_id = derived.annotation_id
    else:
        original = next(r for r in doc.frame_state_records if r.record_id == record_id)
        derived = replace(original, record_id=str(uuid4()), derived_from=record_id, source='manual',
                          review_status='unreviewed' if status == 'needs_review' else status,
                          created_at=_now(), updated_at=_now())
        doc.add_frame_state(derived)
        doc.activate_frame_state(original.frame_index, None if status == 'rejected' else derived.record_id)
        new_id = derived.record_id
    package.review['decisions'].append({**package.provenance(), 'kind':kind, 'cine_id':cine_id,
        'frame_index':original.frame_index, 'derived_from':record_id, 'record_id':new_id, 'status':status, 'at':_now()})
    return new_id


def merge_review(local, package, resolutions=None):
    """Return a new document plus conflicts; never mutate local or auto-promote GT.

    Frame-state candidates live in existing immutable history, without replacing
    the canonical active state pointer. Import history records the candidate IDs.
    """
    resolutions = resolutions or {}
    cine = local.cine_id
    if cine not in package.bases:
        raise ValueError('Review package does not contain this Cine')
    base, remote = package.bases[cine], package.documents[cine]
    standalone = (package.manifest.get('package_format_version') == 2
                  and package.manifest['base_annotation_documents'][cine].get('standalone_empty_base') is True
                  and not base.records.records() and not base.frame_state_records and not base.cine_templates)
    if ((local.document_id != base.document_id and not standalone)
            or local.to_dict()['cine'] != base.to_dict()['cine']):
        raise ValueError('Review base document/Cine identity does not match the local document')
    result = AnnotationDocument.from_dict(local.to_dict())
    # A sparse package is not evidence about the entire Cine. Preserve the
    # reusable template and offsets as an explicit, non-applied review candidate.
    if remote.package_templates:
        template = remote.package_templates['support_structure']
        candidate = {
            'status': 'reviewed_candidate', 'source_scope': 'package',
            'provenance': deepcopy(package.provenance()),
            'available_frames': sorted(row['frame_index'] for row in package.manifest['frames'] if row['cine_id'] == cine),
            'package_templates': remote.package_templates,
            'source_records': [remote.records.get(key).to_dict() for key in template['annotation_ids']],
            'canonical_template_replaced': False,
        }
        if not any(h.get('action') == 'import_package_support_template_candidate' and h.get('candidate') == candidate
                   for h in result.history):
            result._touch('import_package_support_template_candidate', candidate=candidate)
    conflicts, imported = [], []
    base_objects = {r.annotation_id:r for r in base.records.records()}
    remote_objects = {r.annotation_id:r for r in remote.records.records()}
    local_objects = {r.annotation_id:r for r in local.records.records()}
    projections = {}
    for key, record in base_objects.items():
        if record.source == 'imported' and record.attributes.get('creation_tool') == 'cine_template_projection':
            source_id = record.attributes.get('template_source_annotation_id')
            # Verify deterministic materialization against retained source history,
            # even if the user has since changed the active template.
            exported_offset = record.attributes.get('frame_translation', {'dx': 0.0, 'dy': 0.0})
            if source_id not in local_objects or local.support_projection(source_id, record.frame_index, package=True, offset=exported_offset).to_dict() != record.to_dict():
                raise ValueError('Invalid package template projection')
            projections[key] = source_id
            if key in local_objects and local_objects[key].to_dict() != record.to_dict():
                raise ValueError('Local projection history was overwritten')
            continue
        if key not in local_objects or local_objects[key].to_dict() != record.to_dict():
            raise ValueError('Local base record missing or overwritten; manual reconciliation required')
    base_states = {r.record_id:r for r in base.frame_state_records}
    remote_states = {r.record_id:r for r in remote.frame_state_records}
    local_states = {r.record_id:r for r in local.frame_state_records}
    for key, record in base_states.items():
        if key not in local_states or local_states[key] != record:
            raise ValueError('Local base frame-state missing or overwritten')

    def base_ancestor(key, rows, originals):
        seen = set()
        while key and key not in originals:
            if key in seen or key not in rows:
                raise ValueError('Broken reviewer ancestry')
            seen.add(key)
            key = rows[key].derived_from
        return key

    def choose(kind, key, parent, changed, local_rows, remote_record):
        if not changed:
            return 'reviewer'
        conflict_id = kind + ':' + (parent or str(remote_record.frame_index))
        decision = resolutions.get(conflict_id)
        if decision not in (None, 'local', 'reviewer', 'both', 'defer'):
            raise ValueError('Unknown conflict resolution')
        conflicts.append({'conflict_id':conflict_id, 'kind':kind, 'frame_index':remote_record.frame_index,
            'base':(base_objects if kind == 'object' else base_states)[parent].to_dict() if parent else None,
            'local':[r.to_dict() for r in local_rows], 'reviewer':remote_record.to_dict(), 'resolution':decision})
        return decision

    def add_object(key, activate):
        if key in result.record_layers:
            if result.records.get(key).to_dict() != remote_objects[key].to_dict():
                raise ValueError('Reviewer record ID collides with different local content')
            return
        row = remote_objects[key]
        if row.derived_from and row.derived_from not in result.record_layers:
            add_object(row.derived_from, False)
        result.add_record(AnnotationRecord.from_dict(row.to_dict()), 'reviewed', activate=activate)
        imported.append(key)

    decisions = package.review.get('decisions', [])
    rejected_objects = {r['record_id'] for r in decisions if r['cine_id'] == cine and r['kind'] == 'object' and r['status'] == 'rejected'}
    targets = (set(remote.active_annotation_ids) | rejected_objects) - base_objects.keys()
    for key in sorted(targets):
        row = remote_objects[key]
        if key in local_objects:
            if local_objects[key].to_dict() != row.to_dict():
                raise ValueError('Reviewer record ID collides with local content')
            continue
        parent = base_ancestor(key, remote_objects, base_objects)
        if parent in projections:
            source_id = projections[parent]
            local_rows = [r for r in local.support_copies(row.frame_index)
                          if r.attributes.get('template_source_annotation_id') == source_id]
            template = local.cine_templates.get('support_structure', {})
            changed = bool(local_rows) or source_id not in template.get('annotation_ids', []) or not template.get('apply_entire_cine', False)
            changed = changed or local.support_translation(row.frame_index) != base_objects[parent].attributes.get(
                'frame_translation', {'dx': 0.0, 'dy': 0.0})
        else:
            changed = parent is not None and parent not in local.active_annotation_ids
            local_rows = [r for r in local.active_records(row.frame_index)
                          if parent and base_ancestor(r.annotation_id, local_objects, base_objects) == parent]
        choice = choose('object', key, parent, changed, local_rows, row)
        if choice in ('reviewer', 'both'):
            add_object(key, key in remote.active_annotation_ids and row.review_status != 'rejected')
            if choice == 'both':
                for current in local_rows:
                    candidate = result.derive(current.annotation_id, reviewer=package.provenance()['reviewer'])
                    candidate.attributes.update(package.provenance(), import_resolution='keep_both_local_candidate')
                    result.add_record(candidate, 'reviewed')
                    imported.append(candidate.annotation_id)

    def add_state(key):
        if key in {r.record_id for r in result.frame_state_records}:
            existing = next(r for r in result.frame_state_records if r.record_id == key)
            if existing != remote_states[key]:
                raise ValueError('Reviewer frame-state ID collision')
            return
        row = remote_states[key]
        if row.derived_from:
            add_state(row.derived_from)
        result.add_frame_state(row)  # Intentionally no activate_frame_state call.
        imported.append(key)

    rejected_states = {r['record_id'] for r in decisions if r['cine_id'] == cine and r['kind'] == 'state' and r['status'] == 'rejected'}
    for key in sorted((set(remote.active_frame_state_records.values()) | rejected_states)-base_states.keys()):
        row = remote_states[key]
        if key in local_states:
            if local_states[key] != row:
                raise ValueError('Reviewer frame-state ID collision')
            continue
        parent = base_ancestor(key, remote_states, base_states)
        expected = base.active_frame_state_records.get(row.frame_index)
        current = local.frame_state(row.frame_index)
        changed = local.active_frame_state_records.get(row.frame_index) != expected
        choice = choose('state', key, parent, changed, [current] if current else [], row)
        if choice in ('reviewer', 'both'):
            add_state(key)
    if imported:
        result._touch('import_review', package_id=package.manifest['package_id'], reviewer=deepcopy(package.review.get('reviewer')),
                      reviewed_candidate_ids=imported, frame_notes=deepcopy(package.review.get('frame_notes', {})),
                      decisions=deepcopy(decisions), record_provenance=deepcopy(package.review.get('record_provenance', {})),
                      conflicts=deepcopy(conflicts), ground_truth_promoted=False)
    elif not conflicts and not any(h.get('action') == 'import_review_notes' and h.get('package_id') == package.manifest['package_id']
                                   and h.get('frame_notes') == package.review.get('frame_notes', {}) for h in result.history):
        result._touch('import_review_notes', package_id=package.manifest['package_id'],
                      frame_notes=deepcopy(package.review.get('frame_notes', {})), reviewer=deepcopy(package.review.get('reviewer')))
    return result, conflicts
