"""Scheme-owned display metadata. Never added to record geometry."""
from copy import deepcopy
import json
import logging
from pathlib import Path
import re


def validate_display(display, object_ids, state_ids):
    if not isinstance(display, dict):
        raise ValueError('Scheme display must be an object')
    def colors(values):
        if not isinstance(values, list) or not values or not all(
                isinstance(c, str) and re.fullmatch(r'#[0-9a-fA-F]{6}', c) for c in values):
            raise ValueError('Scheme display colors must be nonempty #RRGGBB arrays')
    colors(display.get('palette'))
    if 'daughter_palette' in display:
        colors(display['daughter_palette'])
    for key, known in [('object_order', object_ids), ('common_frame_states', state_ids),
                       ('frame_state_order', state_ids)]:
        values = display.get(key, [])
        if (not isinstance(values, list) or any(not isinstance(v, str) for v in values)
                or len(set(values)) != len(values) or not set(values) <= set(known)):
            raise ValueError('Invalid Scheme display ' + key)
    styles = display.get('object_styles', {})
    if not isinstance(styles, dict) or not set(styles) <= set(object_ids):
        raise ValueError('Scheme object_styles references an unknown label')
    for style in styles.values():
        if not isinstance(style, dict) or style.get('mode') not in ('fixed', 'cycle'):
            raise ValueError('Unknown Scheme style mode')
        colors([style.get('color')] if style['mode'] == 'fixed' else style_colors(display, style))
    for key, known in [('state_names', state_ids), ('object_display_names', object_ids)]:
        names = display.get(key, {})
        if not isinstance(names, dict) or not set(names) <= set(known):
            raise ValueError('Unknown display name in ' + key)
        for names_by_language in names.values():
            if not isinstance(names_by_language, dict) or not all(
                    isinstance(names_by_language.get(lang), str) and names_by_language[lang]
                    for lang in ('zh_CN', 'en_US')):
                raise ValueError('Display names need zh_CN and en_US')
    return deepcopy(display)


def resolve_display(scheme, runtime=False):
    """Return display and warning; old documents inherit current runtime display.

    Invalid styles fall back to neutral, ordered labels without changing the
    embedded scheme snapshot. A caller must surface the returned warning in UI.
    """
    objects = [r['label_id'] for r in scheme['objects']['labels']]
    states = [r['state_id'] for r in scheme['frame_states']['states']]
    try:
        display = scheme.get('display')
        if display is None or (runtime and scheme.get('status') == 'approved_baseline'):
            path = Path(__file__).resolve().parents[3] / 'configs/annotations/droplet_annotation_scheme_v1.json'
            display = json.loads(path.read_text(encoding='utf-8')).get('display')
            display = deepcopy(display)
            # Legacy custom taxonomies may have additional or fewer labels.
            display['object_order'] = [k for k in display['object_order'] if k in objects]
            display['object_styles'] = {k:v for k,v in display['object_styles'].items() if k in objects}
            display['object_display_names'] = {k:v for k,v in display.get('object_display_names', {}).items() if k in objects}
        return validate_display(display, objects, states), None
    except (ValueError, TypeError, KeyError, OSError) as error:
        warning = 'Invalid Scheme display configuration: ' + str(error)
        logging.getLogger(__name__).warning(warning)
        return {'palette':['#808080'], 'object_order':objects, 'object_styles':{},
                'common_frame_states':[], 'frame_state_order':states, 'state_names':{}}, warning


def ordered_ids(available, preferred):
    return [k for k in preferred if k in available] + [k for k in available if k not in preferred]


def label_color(display, label_id):
    style = display.get('object_styles', {}).get(label_id, {})
    return (style_colors(display, style)[0] if style.get('mode') == 'cycle' else
            style.get('color', display['palette'][0]))


def style_colors(display, style):
    """Legacy inline colors remain supported; named palettes have one source."""
    return display.get(style['palette']) if 'palette' in style else style.get('colors')


def record_ordinals(records):
    """Display-only positive ordinals, stable across reload and named derivatives.

    Reserve explicit suffixes first. Unnamed records fill unused numbers in
    deterministic creation/ID order, independently for each Cine/frame/label.
    """
    result, groups = {}, {}
    for record in records:
        groups.setdefault((record.cine_id, record.frame_index, record.label_id), []).append(record)
    for rows in groups.values():
        used = set()
        for row in rows:
            suffix = re.search(r'_(\d+)$', row.attributes.get('instance_name', ''))
            if suffix and int(suffix[1]) > 0:
                result[row.annotation_id] = int(suffix[1])
                used.add(int(suffix[1]))
        number = 1
        for row in sorted(rows, key=lambda r:(r.created_at, r.annotation_id)):
            if row.annotation_id not in result:
                while number in used:
                    number += 1
                result[row.annotation_id] = number
                used.add(number)
    return result


def record_colors(display, records):
    records = list(records)
    result, ordinals = {}, record_ordinals(records)
    for record in sorted(records, key=lambda r:(r.frame_index, r.label_id, r.created_at, r.annotation_id)):
        style = display.get('object_styles', {}).get(record.label_id, {})
        color = label_color(display, record.label_id)
        if style.get('mode') == 'cycle':
            palette = style_colors(display, style)
            color = palette[(ordinals[record.annotation_id]-1) % len(palette)]
        result[record.annotation_id] = color
    return result
