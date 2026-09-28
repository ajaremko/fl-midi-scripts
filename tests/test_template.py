"""
Checks that flc_maschine/controls.py matches the Controller Editor template the MK2 is loaded with.
Run from the FL Complete folder: python3 -m unittest discover -s tests -v
"""

import os
import sys
import unittest
import xml.etree.ElementTree as ET

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path[:0] = [os.path.join(HERE, "fl_stubs"), ROOT]

from flc_maschine import controls  # noqa: E402

TEMPLATE = os.path.join(ROOT, "NI Maschine MK2", "FL Complete.ncm2")

# How the .ncm2 file stores Color Mode = HSB (Single is 0, Dual is 1).
HSB_COLOR_MODE = "3"


def _template_element(midi_map, ref):
    section, index, xml_id = ref
    if section == "controls":
        parent = midi_map.find("controls")
    elif section == "page":
        parent = midi_map.find("pages").findall("page")[index]
    else:
        parent = midi_map.find("groups").findall("group")[index]
    for el in parent:
        if el.get("id") == xml_id and el.get("subtype", "trigger") == "trigger":
            return el
    return None


class TemplateMatchesControls(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.midi_map = ET.parse(TEMPLATE).getroot().find("midi-map")

    def test_every_control_matches_its_template_element(self):
        for control in controls.ALL_CONTROLS:
            with self.subTest(control=control.id):
                el = _template_element(self.midi_map, control.template_ref)
                self.assertIsNotNone(el, "no template element %r" % (control.template_ref,))

                tag = "controller" if control.msg == controls.CC else "note"
                message = el.find(tag)
                self.assertIsNotNone(message, "template sends something other than %s" % tag)
                self.assertEqual(int(message.text), control.number)
                self.assertEqual(int(el.findtext("channel")), control.channel)

                if control.kind == controls.ENCODER:
                    mode = message.get("mode") or controls.ABSOLUTE
                else:
                    mode = el.findtext("behavior")
                self.assertEqual(mode, control.mode)

    def test_pad_pressure_uses_the_pad_note(self):
        pad_page = self.midi_map.find("groups").findall("group")[0]
        for control in controls.ALL_CONTROLS:
            if control.kind != controls.PAD:
                continue
            with self.subTest(control=control.id):
                pressure_id = control.template_ref[2].replace("Pad", "Pressure")
                el = next(e for e in pad_page if e.get("id") == pressure_id)
                self.assertEqual(int(el.findtext("polyat")), control.number)

    def test_colour_leds_are_driven_by_the_script_in_hsb_mode(self):
        # LED On = "For MIDI In" is stored as a <behavior> without onIfDown, and the colour mode on
        # each of the LED's three <led> elements (hue, saturation, brightness).
        pad_page = self.midi_map.find("groups").findall("group")[0]
        for control in controls.ALL_CONTROLS:
            if control.led != controls.HSB:
                continue
            with self.subTest(control=control.id):
                section, index, xml_id = control.template_ref
                button = _template_element(self.midi_map, control.template_ref)
                self.assertIsNone(button.find("behavior").get("onIfDown"), "LED On is not For MIDI In")
                parent = pad_page if section == "pad" else self.midi_map.find("controls")
                leds = [el for el in parent.findall("led") if el.get("id") in (xml_id + "H", xml_id + "S", xml_id + "B")]
                self.assertEqual(len(leds), 3)
                for led in leds:
                    self.assertEqual(led.find("display/unit").get("color-mode"), HSB_COLOR_MODE)

    def test_group_buttons_are_programmable(self):
        # Without this the hardware uses the Group buttons to switch pad pages and sends no MIDI.
        self.assertIsNotNone(self.midi_map.find("handleGroupControls"))

    def test_no_two_controls_share_a_message(self):
        self.assertEqual(len(controls.BY_KEY), len(controls.ALL_CONTROLS))
        self.assertEqual(len(controls.BY_ID), len(controls.ALL_CONTROLS))


if __name__ == "__main__":
    unittest.main()
