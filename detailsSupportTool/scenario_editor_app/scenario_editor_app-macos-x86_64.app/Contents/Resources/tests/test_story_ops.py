import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

from scenario_editor.core import story_ops as S  # noqa: E402

SOUND = {'groups': {'Scenario': {'items': [
    {'name': 'a', 'type': 'VOICE', 'subgroup': 'T'}, {'name': 'b', 'type': 'VOICE', 'subgroup': 'T'},
    {'name': 'c', 'type': 'VOICE'}, {'name': 'se1', 'type': 'SE'}, {'name': 'bg', 'type': 'BGM', 'subgroup': 'X'}]},
    'Other': {'items': [{'name': 'd', 'type': 'VOICE', 'subgroup': 'U'}]}, 'Nul': None}}


class StoryTest(unittest.TestCase):
    def test_options(self):
        o = S.build_options({'groups': {'G': {'items': [{'name': 't', 'sprites': ['s1']}]}}}, SOUND, {'groups': {'E': {'items': [{'name': 'fx'}]}}})
        self.assertEqual(o['img'], [{'group': 'G', 'name': 't', 'sprites': ['s1']}])
        self.assertEqual([i['name'] for i in o['se']], ['se1'])
        self.assertEqual(o['bgm'][0]['group'], 'Scenario')
        self.assertEqual(o['voiceSeries'], [{'group': 'Scenario', 'subGroup': 'T', 'count': 2}, {'group': 'Other', 'subGroup': 'U', 'count': 1}])
        self.assertEqual(S.voice_series_label(o['voiceSeries'][0]), 'Sound_Scenario_T（VOICE 2件）')
        self.assertEqual(S.option_label(o['bgm'][0]), 'Scenario / X / bg')
        self.assertEqual(S.option_label(o['se'][0]), 'Scenario / se1')
        self.assertEqual(S.build_options(None, None, None)['voiceSeries'], [])

    def test_slots(self):
        defs = [{'prefix': 'img', 'names': ['img_0', 'img_1']}, {'prefix': 'sound_se', 'names': ['sound_se_0']}]
        slots = []
        asset = {'group': 'G', 'name': 't', 'subgroup': ''}
        slots = S.add_slot(slots, 'img', 'img_0', asset, 'sp', True)
        self.assertEqual(slots, [{'slot': 'img_0', 'kind': 'img', 'group': 'G', 'subGroup': None, 'id': 't', 'spriteName': 'sp', 'retain': True}])
        self.assertEqual(S.available_slot_names(defs, slots, 'img'), ['img_1'])
        self.assertEqual(S.available_slot_names(defs, slots, 'se'), ['sound_se_0'])
        self.assertEqual(S.available_slot_names(defs, slots, 'bgm'), [])
        slots = S.add_slot(slots, 'se', 'sound_se_0', asset, 'ignored')
        self.assertNotIn('spriteName', slots[1])
        self.assertEqual(S.add_slot(slots, 'se', '', asset), slots)
        self.assertEqual(S.add_slot(slots, 'se', 'x', None), slots)
        self.assertEqual(S.add_slot([], 'img', 'img_0', asset)[0]['spriteName'], None)
        self.assertEqual(S.slots_for_kind(slots, 'se')[0]['slot'], 'sound_se_0')
        slots = S.toggle_retain(slots, 'sound_se_0')
        self.assertTrue(slots[1]['retain'])
        self.assertEqual(S.slot_summary(slots[0]), 'G / t (Sprite: sp)')
        self.assertEqual(S.slot_summary(slots[1]), 'G / t')
        self.assertEqual(len(S.remove_slot(slots, 'img_0')), 1)

    def test_voice(self):
        opts = [{'group': 'A', 'subGroup': 'B', 'count': 1}]
        v = S.select_voice_series({'group': 'x', 'subGroup': 'y', 'retain': True}, opts[0])
        self.assertEqual(v, {'group': 'A', 'subGroup': 'B', 'retain': True})
        self.assertIsNone(S.select_voice_series(v, None))
        self.assertEqual(S.set_voice_retain(v, False)['retain'], False)
        self.assertIsNone(S.set_voice_retain(None, True))
        self.assertEqual(S.find_voice_option(v, opts), opts[0])
        self.assertIsNone(S.find_voice_option(None, opts))
        self.assertEqual(S.save_body([], None), {'slots': [], 'voiceSeriesId': None})


if __name__ == '__main__':
    unittest.main()
