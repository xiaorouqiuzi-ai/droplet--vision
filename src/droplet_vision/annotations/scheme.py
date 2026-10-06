"""Qt-free scheme loading. Custom copies retain IDs and embed display overrides."""
from __future__ import annotations
import json
from pathlib import Path
from .schema import AnnotationLabel, _json_copy


CONFIG_DIR = Path(__file__).resolve().parents[3] / 'configs/annotations'


def load_state_schema():
    return json.loads((CONFIG_DIR / 'frame_state_v1.json').read_text(encoding='utf-8'))


def load_scheme(path=None):
    path = Path(path or CONFIG_DIR / 'droplet_annotation_scheme_v1.json')
    value = json.loads(path.read_text(encoding='utf-8'))
    if value.get('schema_version') != 1 or not value.get('scheme_id'):
        raise ValueError('Unsupported annotation scheme')
    for key, field in [('object_taxonomy', 'objects'), ('frame_state_schema', 'frame_states')]:
        if field not in value:
            reference = value[key]
            if Path(reference).name != reference or '\\' in reference or ':' in reference:
                raise ValueError('Scheme references must be sibling filenames')
            value[field] = json.loads((path.parent / reference).read_text(encoding='utf-8'))
    return validate_scheme(value)


def validate_scheme(value):
    value = _json_copy(value)
    if (value.get('schema_version') != 1 or not isinstance(value.get('scheme_id'), str)
            or not value['scheme_id'] or not all(isinstance(value.get('display_name', {}).get(key), str)
                                               for key in ('zh_CN', 'en_US'))):
        raise ValueError('Invalid scheme identity/display metadata')
    labels = [AnnotationLabel(**row) for row in value['objects']['labels']]
    if len({label.label_id for label in labels}) != len(labels):
        raise ValueError('Duplicate object ID')
    expected = load_state_schema()
    states = value['frame_states']
    if ([row['state_id'] for row in states['states']] != [row['state_id'] for row in expected['states']]
            or states['quality_flags'] != expected['quality_flags']
            or states.get('exclusive_state_id') != expected['exclusive_state_id']):
        raise ValueError('Custom schemes must preserve v1 state and quality IDs/rules')
    for row in states['states']:
        if (row['group'] not in ('core', 'dynamic') or type(row['enabled']) is not bool
                or not all(isinstance(row[key], str) and row[key] for key in ('display_name_en', 'display_name_zh'))):
            raise ValueError('Invalid state display configuration')
    if value.get('status') == 'approved_baseline' or value['scheme_id'] == 'droplet_annotation_scheme_v1':
        canonical = json.loads((CONFIG_DIR / 'droplet_annotation_scheme_v1.json').read_text(encoding='utf-8'))
        canonical['objects'] = json.loads((CONFIG_DIR / canonical['object_taxonomy']).read_text(encoding='utf-8'))
        canonical['frame_states'] = expected
        # Display revisions are runtime style configuration, not semantic IDs.
        # Legacy snapshots without display remain valid and retain provenance.
        if {k:v for k,v in value.items() if k != 'display'} != {k:v for k,v in canonical.items() if k != 'display'}:
            raise ValueError('Approved baseline was changed; use a new custom scheme ID')
    from .display_style import resolve_display
    resolve_display(value)  # Validate and log; UI exposes warning and safe fallback.
    return value


def save_custom_scheme(value, path):
    """Never overwrite a scheme or anything in the approved configuration directory."""
    path = Path(path).resolve()
    if CONFIG_DIR.resolve() in path.parents or path.suffix.lower() != '.json':
        raise ValueError('Save a new custom JSON outside approved configs')
    value = _json_copy(value)
    if value.get('status') == 'approved_baseline' or value.get('scheme_id') == 'droplet_annotation_scheme_v1':
        raise ValueError('Approved baseline cannot be overwritten; create a custom scheme ID')
    value = validate_scheme(value)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('x', encoding='utf-8') as handle:
        json.dump(value, handle, ensure_ascii=False, indent=2, allow_nan=False)
        handle.write('\n')


def suggest_instance_name(document, frame_index, label_id, prefixes):
    prefix = prefixes.get(label_id, label_id)
    used = {r.attributes.get('instance_name') for r in document.active_records(frame_index)}
    index = 1
    while f'{prefix}_{index:02d}' in used:
        index += 1
    return f'{prefix}_{index:02d}'
