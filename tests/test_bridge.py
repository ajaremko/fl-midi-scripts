"""
Tests the MK2 bridge's routing without MIDI ports (mido isn't needed).
Run from the FL Complete folder: python3 -m unittest discover -s tests -v
"""

import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "mk2_bridge"))

import bridge  # noqa: E402


class Msg:
    """Stands in for a mido message: only `type` matters to the bridge."""

    def __init__(self, type, **fields):
        self.type = type
        self.fields = fields

    def __repr__(self):
        return "Msg(%s, %s)" % (self.type, self.fields)


class BridgeTest(unittest.TestCase):
    def setUp(self):
        self.to_fl = []
        self.to_device = []
        self.bridge = bridge.Bridge(self.to_fl.append, self.to_device.append)

    def test_device_messages_pass_to_fl_unchanged(self):
        for msg in (Msg("note_on", note=12, velocity=90), Msg("control_change", control=101, value=1),
                    Msg("polytouch", note=12, value=40), Msg("sysex", data=(1, 2))):
            self.bridge.from_device(msg)
        self.assertEqual([m.type for m in self.to_fl], ["note_on", "control_change", "polytouch", "sysex"])
        self.assertEqual(self.to_device, [])

    def test_fl_messages_pass_to_the_device(self):
        led = Msg("control_change", channel=1, control=12, value=127)
        self.bridge.from_fl(led)
        self.assertEqual(self.to_device, [led])
        self.assertEqual(self.to_fl, [])

    def test_fl_clock_and_transport_sync_are_not_sent_to_the_device(self):
        for kind in ("clock", "start", "stop", "continue", "songpos", "active_sensing", "reset"):
            self.bridge.from_fl(Msg(kind))
        self.assertEqual(self.to_device, [])

    def test_a_failed_send_is_logged_not_raised(self):
        def broken(msg):
            raise IOError("port closed")

        b = bridge.Bridge(broken, broken)
        with self.assertLogs("mk2_bridge", "ERROR"):
            b.from_device(Msg("note_on"))


class FindPortTest(unittest.TestCase):
    NAMES = ["Maschine MK2 In 0", "MK2 Bridge In 1", "MK2 Bridge Out 2", "FL STUDIO FIRE 3"]

    def test_finds_the_one_match(self):
        self.assertEqual(bridge.find_port(self.NAMES, "maschine mk2"), "Maschine MK2 In 0")

    def test_excludes_the_bridge_ports(self):
        self.assertEqual(bridge.find_port(self.NAMES, "MK2", exclude=("MK2 Bridge In", "MK2 Bridge Out")),
                         "Maschine MK2 In 0")

    def test_no_match_lists_the_ports(self):
        with self.assertRaisesRegex(bridge.PortError, "FL STUDIO FIRE"):
            bridge.find_port(self.NAMES, "Launchpad")

    def test_several_matches_is_an_error(self):
        with self.assertRaisesRegex(bridge.PortError, "more than one"):
            bridge.find_port(self.NAMES, "MK2")


class MainTest(unittest.TestCase):
    def test_without_mido_it_explains_what_to_install(self):
        saved = sys.modules.get("mido")
        sys.modules["mido"] = None  # makes "import mido" raise ImportError
        try:
            with self.assertLogs("mk2_bridge", "ERROR") as logs:
                self.assertEqual(bridge.main([]), 1)
        finally:
            if saved is None:
                del sys.modules["mido"]
            else:
                sys.modules["mido"] = saved
        self.assertIn("pip install", logs.output[0])


if __name__ == "__main__":
    unittest.main()
