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
    """Stands in for a mido message: a type and fields as attributes."""

    def __init__(self, type, **fields):
        self.type = type
        self.fields = fields
        for name, value in fields.items():
            setattr(self, name, value)

    def __eq__(self, other):
        return isinstance(other, Msg) and (self.type, self.fields) == (other.type, other.fields)

    def __repr__(self):
        return "Msg(%s, %s)" % (self.type, self.fields)


def cc16(control, value):
    """A channel-16 control change from the script to the bridge."""
    return Msg("control_change", channel=bridge.CONTROL_CHANNEL, control=control, value=value)


class BridgeTest(unittest.TestCase):
    def setUp(self):
        self.to_fl = []
        self.to_device = []
        self.now = 0.0
        self.bridge = bridge.Bridge(self.to_fl.append, self.to_device.append, make_message=Msg,
                                    clock=lambda: self.now)

    def test_device_messages_pass_to_fl_unchanged(self):
        for msg in (Msg("note_on", channel=0, note=12, velocity=90), Msg("control_change", channel=0, control=101, value=1),
                    Msg("polytouch", channel=0, note=12, value=40), Msg("sysex", data=(1, 2))):
            self.bridge.from_device(msg)
        self.assertEqual([m.type for m in self.to_fl], ["note_on", "control_change", "polytouch", "sysex"])
        self.assertEqual(self.to_device, [])

    def test_fl_messages_pass_to_the_device(self):
        led = Msg("control_change", channel=1, control=12, value=127)
        self.bridge.from_fl(led)
        self.assertEqual(self.to_device, [led])
        self.assertEqual(self.to_fl, [])

    def test_fl_clock_and_transport_sync_are_not_sent_to_the_device(self):
        for kind in ("clock", "start", "stop", "continue", "active_sensing", "reset"):
            self.bridge.from_fl(Msg(kind))
        self.bridge.from_fl(Msg("songpos", pos=0))
        self.assertEqual(self.to_device, [])

    def test_a_failed_send_is_logged_not_raised(self):
        def broken(msg):
            raise IOError("port closed")

        b = bridge.Bridge(broken, broken)
        with self.assertLogs("mk2_bridge", "ERROR"):
            b.from_device(Msg("control_change", channel=0, control=101, value=1))

    def test_script_state_is_kept_by_the_bridge(self):
        self.bridge.from_fl(cc16(bridge.CC_REPEAT, 127))
        self.assertTrue(self.bridge.repeater.enabled)
        self.assertEqual(self.to_device, [])  # not passed to the MK2

    def test_clock_messages_drive_the_repeater(self):
        self.bridge.from_fl(Msg("start"))
        self.bridge.from_fl(Msg("clock"))
        self.bridge.from_fl(Msg("songpos", pos=4))
        self.assertEqual(self.bridge.repeater.position, 24)
        self.assertEqual(self.bridge.repeater.last_clock, 0.0)
        self.bridge.from_fl(Msg("stop"))
        self.assertTrue(self.bridge.repeater.stopped)

    def test_hello(self):
        self.bridge.hello()
        self.assertEqual(self.to_fl, [cc16(bridge.CC_HELLO, 127)])

    def test_note_repeat_replays_a_held_pad(self):
        self.bridge.from_fl(cc16(bridge.CC_REPEAT, 127))
        press = Msg("note_on", channel=0, note=12, velocity=90)
        self.bridge.from_device(press)
        self.assertEqual(self.to_fl, [press])
        self.now = 0.07  # past the gate (step at 120 BPM: 0.125 s)
        self.bridge.tick()
        self.now = 0.13
        self.bridge.tick()
        self.assertEqual(self.to_fl[1:], [Msg("note_off", channel=0, note=12, velocity=0),
                                          Msg("note_on", channel=0, note=12, velocity=90)])
        self.bridge.from_device(Msg("note_off", channel=0, note=12, velocity=0))
        self.assertEqual(self.to_fl[-1].type, "note_off")  # the note was on: release passed through


class BridgeNoClockTest(unittest.TestCase):
    def test_the_warning_goes_to_the_script_on_channel_16(self):
        to_fl = []
        now = [0.0]
        b = bridge.Bridge(to_fl.append, lambda m: None, make_message=Msg, clock=lambda: now[0])
        b.from_fl(cc16(bridge.CC_REPEAT, 127))
        b.from_fl(cc16(bridge.CC_PLAYING, 127))
        b.from_device(Msg("note_on", channel=0, note=12, velocity=90))
        with self.assertLogs("mk2_bridge", "WARNING"):
            for t in (0.01, 0.3):
                now[0] = t
                b.tick()
        self.assertIn(cc16(bridge.CC_NO_CLOCK, 127), to_fl)


class BridgeFirstNoteTest(unittest.TestCase):
    def test_a_held_back_press_is_not_sent_and_plays_on_the_grid_line(self):
        to_fl = []
        now = [0.0]
        b = bridge.Bridge(to_fl.append, lambda m: None, make_message=Msg, clock=lambda: now[0])
        b.from_fl(cc16(bridge.CC_REPEAT, 127))
        b.from_fl(Msg("start"))
        b.from_fl(Msg("clock"))  # line 0 at t = 0
        now[0] = 0.05
        b.from_device(Msg("note_on", channel=0, note=12, velocity=90))
        self.assertEqual(to_fl, [])  # held back
        for pos in range(1, 7):
            now[0] = 0.05 + pos * 0.02
            b.from_fl(Msg("clock"))
        self.assertEqual(to_fl, [Msg("note_on", channel=0, note=12, velocity=90)])  # on line 6


class PressureThinningTest(unittest.TestCase):
    def setUp(self):
        self.to_fl = []
        self.now = 0.0
        self.b = bridge.Bridge(self.to_fl.append, lambda m: None, make_message=Msg, clock=lambda: self.now)

    def press(self, value, note=12):
        self.b.from_device(Msg("polytouch", channel=0, note=note, value=value))

    def values(self):
        return [m.value for m in self.to_fl if m.type == "polytouch"]

    def test_repeated_values_are_dropped(self):
        self.press(40)
        self.now = 0.02
        self.press(40)
        self.assertEqual(self.values(), [40])

    def test_at_most_one_per_interval_and_the_latest_follows(self):
        self.press(40)
        self.now = 0.003
        self.press(50)
        self.now = 0.006
        self.press(60)
        self.assertEqual(self.values(), [40])
        self.assertTrue(self.b.busy)  # the timer has pressure to send
        self.now = 0.009
        self.b.tick()
        self.assertEqual(self.values(), [40])  # interval not up yet
        self.now = 0.011
        self.b.tick()
        self.assertEqual(self.values(), [40, 60])  # the latest, not 50
        self.assertFalse(self.b.busy)

    def test_zero_always_goes_at_once(self):
        self.press(40)
        self.now = 0.002
        self.press(0)
        self.assertEqual(self.values(), [40, 0])

    def test_release_drops_pending_pressure(self):
        self.press(40)
        self.now = 0.003
        self.press(70)
        self.b.from_device(Msg("note_off", channel=0, note=12, velocity=0))
        self.now = 0.02
        self.b.tick()
        self.assertEqual(self.values(), [40])

    def test_pads_are_thinned_separately_and_other_messages_never(self):
        self.press(40, note=12)
        self.press(40, note=13)
        self.b.from_device(Msg("control_change", channel=0, control=101, value=1))
        self.b.from_device(Msg("control_change", channel=0, control=101, value=1))
        self.assertEqual(self.values(), [40, 40])
        self.assertEqual(len([m for m in self.to_fl if m.type == "control_change"]), 2)

    def test_heavy_traffic_is_logged(self):
        with self.assertLogs("mk2_bridge", "WARNING") as logs:
            for i in range(bridge.FLOOD_WARN + 1):
                self.b.from_device(Msg("control_change", channel=0, control=101, value=i % 128))
            self.now = 1.0
            self.b.from_device(Msg("control_change", channel=0, control=101, value=1))
        self.assertIn("heavy MIDI to FL: %d msg/s" % (bridge.FLOOD_WARN + 1), logs.output[0])

    def test_normal_traffic_is_not_logged(self):
        logger = bridge.log
        with self.assertRaises(AssertionError):  # no warning logged
            with self.assertLogs(logger, "WARNING"):
                for i in range(bridge.FLOOD_WARN):
                    self.b.from_device(Msg("control_change", channel=0, control=101, value=1))
                self.now = 1.0
                self.b.from_device(Msg("control_change", channel=0, control=101, value=1))


class NoteRepeaterTest(unittest.TestCase):
    """Rate 6 clocks (a sixteenth) at 120 BPM: 0.125 s per repeat, gate 0.0625 s or 3 clocks."""

    def setUp(self):
        self.notes = []
        self.r = bridge.NoteRepeater(lambda kind, ch, note, vel: self.notes.append((kind, note, vel)))
        self.r.control_change(bridge.CC_REPEAT, 127)

    def hits(self):
        return [n for n in self.notes if n[0] == "note_on"]

    def run_clocks(self, first, last, start_time=0.0):
        """Send clocks at positions first..last, 20 ms apart."""
        for i, _ in enumerate(range(first, last + 1)):
            self.r.clock(start_time + i * 0.02)

    def test_off_passes_everything_and_tracks_nothing(self):
        self.r.control_change(bridge.CC_REPEAT, 0)
        self.assertTrue(self.r.pad_on(0, 12, 90, 0.0))
        self.r.tick(1.0)
        self.assertEqual(self.notes, [])
        self.assertTrue(self.r.pad_off(0, 12, 1.0))

    def test_timer_mode_repeats_with_a_half_gate(self):
        self.assertTrue(self.r.pad_on(0, 12, 90, 0.0))  # the press itself goes to FL
        self.r.tick(0.05)
        self.assertEqual(self.notes, [])
        self.r.tick(0.07)
        self.assertEqual(self.notes, [("note_off", 12, 0)])
        self.r.tick(0.13)
        self.assertEqual(self.notes[-1], ("note_on", 12, 90))
        self.r.tick(0.26)
        self.assertEqual(len(self.hits()), 2)

    def test_release_is_passed_only_while_the_note_is_on(self):
        self.r.pad_on(0, 12, 90, 0.0)
        self.r.tick(0.07)  # gate off
        self.assertFalse(self.r.pad_off(0, 12, 0.08))  # already off: drop the release
        self.r.pad_on(0, 13, 90, 0.0)
        self.assertTrue(self.r.pad_off(0, 13, 0.01))  # still on: pass it
        self.r.tick(1.0)
        self.assertEqual(self.hits(), [])  # both stopped

    def test_rate_and_tempo_are_applied_on_the_lsb(self):
        self.r.control_change(bridge.CC_RATE, 0)
        self.r.control_change(bridge.CC_RATE_LSB, 24)  # a beat
        self.r.control_change(bridge.CC_TEMPO, 5)
        self.r.control_change(bridge.CC_TEMPO_LSB, 0)  # 640 -> 64.0 BPM
        self.assertEqual(self.r.rate, 24)
        self.assertEqual(self.r.bpm, 64.0)
        self.assertAlmostEqual(self.r.interval(), 60 / 64.0)
        self.r.control_change(bridge.CC_RATE, 1)
        self.assertEqual(self.r.rate, 24)  # MSB alone changes nothing
        self.r.control_change(bridge.CC_RATE_LSB, 0)
        self.assertEqual(self.r.rate, 128)

    def test_clock_mode_hits_on_the_grid(self):
        self.r.start()
        self.run_clocks(0, 1)  # positions 0, 1 (a grid line at 0, t = 0)
        # Pressed 30 ms after line 0: past the grace window (1/8 of 0.125 s), so it's held back.
        self.assertFalse(self.r.pad_on(0, 12, 90, 0.03))
        self.run_clocks(2, 13, start_time=0.04)
        # First note on line 6, note-off 3 clocks later (9), then line 12.
        self.assertEqual(self.notes, [("note_on", 12, 90), ("note_off", 12, 0), ("note_on", 12, 90)])

    def test_press_just_after_a_grid_line_plays_at_once_and_counts_as_it(self):
        self.r.start()
        self.run_clocks(0, 6)  # line 6 at t = 0.12
        self.assertTrue(self.r.pad_on(0, 12, 90, 0.125))  # 5 ms after it: within the grace window
        self.assertEqual(self.hit_positions(range(7, 19)), [12, 18])  # 6 isn't hit again

    def test_press_just_before_a_grid_line_plays_on_it(self):
        self.r.start()
        self.run_clocks(0, 4)
        self.assertFalse(self.r.pad_on(0, 12, 90, 0.09))  # next clock is 5; line 6 is next
        self.assertEqual(self.hit_positions(range(5, 13)), [6, 12])

    def test_a_quick_tap_still_plays_one_note_on_the_grid(self):
        self.r.start()
        self.run_clocks(0, 2)
        self.assertFalse(self.r.pad_on(0, 12, 90, 0.045))
        self.assertFalse(self.r.pad_off(0, 12, 0.05))  # released before line 6: not passed on
        self.assertEqual(self.hit_positions(range(3, 19)), [6])  # one note, no repeats
        self.assertEqual(self.notes, [("note_on", 12, 90), ("note_off", 12, 0)])  # gate at 9
        self.assertFalse(self.r.busy)  # done with

    def test_a_held_back_note_plays_at_once_if_the_clock_stops(self):
        self.r.start()
        self.run_clocks(0, 2)
        self.r.pad_on(0, 12, 90, 0.045)
        self.r.stop()
        self.r.tick(0.05)
        self.assertEqual(self.hits(), [("note_on", 12, 90)])

    def test_a_held_back_tap_plays_and_ends_on_the_timer_if_the_clock_stops(self):
        self.r.start()
        self.run_clocks(0, 2)
        self.r.pad_on(0, 12, 90, 0.045)
        self.r.pad_off(0, 12, 0.05)
        self.r.stop()
        self.r.tick(0.06)
        self.r.tick(0.06 + self.r.interval() * bridge.GATE + 0.001)
        self.assertEqual(self.notes, [("note_on", 12, 90), ("note_off", 12, 0)])
        self.assertFalse(self.r.busy)

    def test_the_grace_window_scales_with_the_rate_and_is_capped(self):
        self.assertAlmostEqual(self.r.grace(), 0.125 * 0.125)  # 1/16 at 120 BPM
        self.r.control_change(bridge.CC_RATE, 0)
        self.r.control_change(bridge.CC_RATE_LSB, 24)  # 1/4: 0.5 s
        self.assertEqual(self.r.grace(), bridge.GRACE_MAX)

    def test_song_position_jump_hits_the_next_grid_line(self):
        self.r.start()
        self.run_clocks(0, 1)
        self.r.pad_on(0, 12, 90, 0.03)
        self.r.songpos(0)  # a jump back to the start, well after the press
        self.run_clocks(0, 0, start_time=0.1)
        self.assertEqual(self.hits(), [("note_on", 12, 90)])

    def test_loop_wrap_hits_once_on_the_downbeat(self):
        # A 1-bar loop: the clock at 96 (end of the bar, a grid line) is followed a few ms later by
        # song position 0 and the clock at 0 (also a grid line). One note, not two.
        self.r.start()
        self.r.pad_on(0, 12, 90, 0.0)
        t = 0.0
        for pos in range(0, 97):
            t = pos * 0.02
            self.r.clock(t)
        before = len(self.hits())
        self.r.songpos(0)
        self.r.clock(t + 0.003)
        self.assertEqual(len(self.hits()), before)  # 96 hit; 0 is too close to it
        for pos in range(1, 7):
            self.r.clock(t + 0.003 + pos * 0.02)
        self.assertEqual(len(self.hits()), before + 1)  # then 6 hits as usual

    def test_a_position_resent_where_a_pad_just_hit_does_not_hit_again(self):
        self.r.start()
        self.r.pad_on(0, 12, 90, 0.0)
        self.run_clocks(0, 12)  # hits at 6 and 12
        hits = len(self.hits())
        self.r.songpos(2)  # position 12 again
        self.r.clock(1.0)  # long after, but the same position
        self.assertEqual(len(self.hits()), hits)

    def hit_positions(self, positions):
        """Send clocks at the given positions (20 ms each), returning those where a pad hit."""
        hit = []
        for pos in positions:
            before = len(self.hits())
            self.r.clock(pos * 0.02)
            if len(self.hits()) > before:
                hit.append(pos)
        return hit

    def test_rate_change_in_clock_mode_follows_the_new_grid(self):
        self.r.start()
        self.r.pad_on(0, 12, 90, 0.0)
        self.assertEqual(self.hit_positions(range(0, 7)), [6])
        self.r.control_change(bridge.CC_RATE, 0)
        self.r.control_change(bridge.CC_RATE_LSB, 8)  # 1/8T: 0.167 s at 120 BPM
        # Line 8 is only 40 ms after the hit at 6 (less than half an interval), so the next hit
        # is line 16, then every 8 clocks.
        self.assertEqual(self.hit_positions(range(7, 33)), [16, 24, 32])

    def test_rate_change_on_the_timer_counts_from_the_last_hit(self):
        self.r.pad_on(0, 12, 90, 0.0)  # 1/16: next hit due at 0.125
        self.r.tick(0.1)
        self.r.control_change(bridge.CC_RATE, 0)
        self.r.control_change(bridge.CC_RATE_LSB, 3)  # 1/32: 0.0625 from the press, already due
        self.r.tick(0.101)
        self.assertEqual(len(self.hits()), 1)
        self.r.tick(0.101 + 0.0625)
        self.assertEqual(len(self.hits()), 2)

    def test_no_clock_while_playing_warns_once(self):
        warnings = []
        r = bridge.NoteRepeater(lambda *a: None, on_no_clock=lambda: warnings.append(1))
        r.control_change(bridge.CC_REPEAT, 127)
        r.control_change(bridge.CC_PLAYING, 127)
        r.pad_on(0, 12, 90, 0.0)
        r.tick(0.1)
        self.assertEqual(warnings, [])  # not yet: the clock may be about to start
        r.tick(0.4)
        r.tick(0.8)
        self.assertEqual(warnings, [1])  # once per play
        r.control_change(bridge.CC_PLAYING, 0)
        r.control_change(bridge.CC_PLAYING, 127)
        r.tick(1.0)
        r.tick(1.3)
        self.assertEqual(warnings, [1, 1])  # again for a new play

    def test_no_warning_while_the_clock_arrives(self):
        warnings = []
        r = bridge.NoteRepeater(lambda *a: None, on_no_clock=lambda: warnings.append(1))
        r.control_change(bridge.CC_REPEAT, 127)
        r.control_change(bridge.CC_PLAYING, 127)
        r.start()
        r.pad_on(0, 12, 90, 0.0)
        for i in range(50):
            r.clock(i * 0.02)
            r.tick(i * 0.02 + 0.001)
        self.assertEqual(warnings, [])

    def test_stop_or_a_silent_clock_falls_back_to_the_timer(self):
        self.r.start()
        self.run_clocks(0, 1)
        self.r.stop()
        self.r.pad_on(0, 12, 90, 0.05)
        self.assertIsNotNone(self.r.pads[(0, 12)].next_hit)  # timer mode
        self.r.cont()
        self.r.clock(0.06)
        self.assertTrue(self.r.clocked(0.06))
        self.assertFalse(self.r.clocked(0.06 + bridge.CLOCK_TIMEOUT + 0.01))
        self.r.tick(0.5)  # clock gone: the timer takes over, and the overdue hit plays at once
        self.assertEqual(len(self.hits()), 1)
        self.r.tick(0.5 + self.r.interval() + 0.001)  # then on at the interval
        self.assertEqual(len(self.hits()), 2)

    def test_turning_off_releases_held_notes(self):
        self.r.pad_on(0, 12, 90, 0.0)
        self.r.control_change(bridge.CC_REPEAT, 0)
        self.assertEqual(self.notes, [("note_off", 12, 0)])
        self.assertFalse(self.r.busy)
        self.assertTrue(self.r.pad_off(0, 12, 0.1))  # the real release passes, harmlessly
        self.r.tick(1.0)
        self.assertEqual(len(self.notes), 1)

    def test_pads_repeat_independently(self):
        self.r.pad_on(0, 12, 90, 0.0)
        self.r.pad_on(0, 13, 60, 0.05)
        self.r.tick(0.13)
        self.r.tick(0.18)
        self.assertEqual(self.hits(), [("note_on", 12, 90), ("note_on", 13, 60)])


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
