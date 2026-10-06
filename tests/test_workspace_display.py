import json
import unittest
from copy import deepcopy
from droplet_vision.annotations.scheme import load_scheme, validate_scheme
from droplet_vision.annotations.display_style import validate_display, resolve_display, record_colors, label_color, record_ordinals
from droplet_vision.annotations.schema import AnnotationRecord


class SchemeDisplayTests(unittest.TestCase):
    def setUp(self):
        self.scheme = load_scheme()
        self.display = self.scheme['display']
        self.ids = [r['label_id'] for r in self.scheme['objects']['labels']]
        self.states = [r['state_id'] for r in self.scheme['frame_states']['states']]

    def test_palette_fixed_and_daughter_suffixes(self):
        self.assertEqual(self.display['palette'], ['#3B6FB6','#2A9D8F','#E9A23B','#7A6FAC','#D96C75','#7B8794'])
        records = [AnnotationRecord('cine',0,'daughter_droplet','point',{'point':[5,5]},
                    attributes={'instance_name':f'Daughter_{n:02d}'}) for n in range(1,7)]
        colors = record_colors(self.display, records)
        self.assertEqual([colors[r.annotation_id] for r in records],self.display['daughter_palette'])
        self.assertEqual(colors,record_colors(self.display,list(reversed(records))))
        changed = AnnotationRecord('cine',0,'daughter_droplet','point',{'point':[6,6]},
                                  attributes={'instance_name':'Daughter_03'}, derived_from=records[2].annotation_id)
        self.assertEqual(record_colors(self.display,[changed])[changed.annotation_id],colors[records[2].annotation_id])

    def test_unnamed_deterministic_and_geometry_unmodified(self):
        records = [AnnotationRecord('cine',0,'daughter_droplet','point',{'point':[5,5]}) for _ in range(4)]
        before = [r.to_dict() for r in records]
        colors = record_colors(self.display,records)
        self.assertEqual(colors,record_colors(self.display,list(reversed(records))))
        self.assertEqual(before,[r.to_dict() for r in records])

    def test_v16_fixed_mapping_and_display_name_validation(self):
        expected = {'parent_droplet':'#3B6FB6','internal_cavity_candidate':'#7A6FAC',
                    'daughter_droplet':'#2A9D8F','flame':'#E9A23B',
                    'support_structure':'#7B8794','soot':'#D96C75'}
        self.assertEqual({k:label_color(self.display,k) for k in expected},expected)
        self.assertEqual(self.display['object_order'][-1],'soot')
        for field,value in [('daughter_palette',[]), ('daughter_palette',['bad']),
                            ('object_display_names',{'unknown':{'zh_CN':'未知','en_US':'Unknown'}}),
                            ('object_display_names',{'parent_droplet':{'en_US':'Parent'}})]:
            display=deepcopy(self.display);display[field]=value
            with self.assertRaises(ValueError):validate_display(display,self.ids,self.states)

    def test_display_revision_does_not_break_legacy_or_semantic_validation(self):
        old = deepcopy(self.scheme);old.pop('display')
        self.assertEqual(validate_scheme(old),old)
        edited = deepcopy(self.scheme);edited['display']['object_styles']['parent_droplet']['color']='#112233'
        self.assertEqual(validate_scheme(edited),edited)
        bad = deepcopy(old);bad['objects']['labels'][0]['label_id']='changed_semantics'
        with self.assertRaises(ValueError):validate_scheme(bad)

    def test_invalid_colors_order_states_styles_fall_back_with_warning(self):
        bad_values = [('palette',['red']), ('object_order',['unknown']),
                      ('common_frame_states',['uncertain']), ('object_styles',{'unknown':{'mode':'fixed','color':'#123456'}}),
                      ('object_styles',{'daughter_droplet':{'mode':'cycle','colors':[]}})]
        for key,value in bad_values:
            with self.subTest(key=key,value=value):
                scheme=deepcopy(self.scheme);scheme['display'][key]=value
                with self.assertRaises(ValueError):validate_display(scheme['display'],self.ids,self.states)
                with self.assertLogs('droplet_vision.annotations.display_style',level='WARNING'):
                    fallback,warning=resolve_display(scheme)
                self.assertTrue(warning);self.assertEqual(fallback['palette'],['#808080'])
                json.dumps(validate_scheme(scheme))
