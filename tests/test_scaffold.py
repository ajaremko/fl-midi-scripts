"""
Drives the entry script end to end with stand-ins for FL Studio's modules.
Run from the FL Complete folder: python3 -m unittest discover -s tests -v
"""

import contextlib
import io
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path[:0] = [os.path.join(HERE, "fl_stubs"), ROOT]

import channels  # noqa: E402  (the stub)
import device  # noqa: E402  (the stub)
import general  # noqa: E402  (the stub)
import plugins  # noqa: E402  (the stub)
import transport  # noqa: E402  (the stub)
import ui  # noqa: E402  (the stub)
import midi  # noqa: E402

import device_FLC_MaschineMK2 as script  # noqa: E402
from flc_maschine import controls, log, notes  # noqa: E402
from flc_maschine.controller import MaschineMk2  # noqa: E402
from flc_maschine.rendering import colors, renderer  # noqa: E402
from flc_maschine.handlers import transport_controls  # noqa: E402
from flc_maschine.rendering.fl_state import FlSnapshot  # noqa: E402


class FakeEvent:
    def __init__(self, midi_id, data1, data2, channel=0):
        self.midiId = midi_id
        self.midiChan = channel
        self.status = midi_id + channel
        self.data1 = data1
        self.data2 = data2
        self.handled = False


def cc(number, value=127):
    return FakeEvent(midi.MIDI_CONTROLCHANGE, number, value)


def note_on(number, velocity=100):
    return FakeEvent(midi.MIDI_NOTEON, number, velocity)


def note_off(number):
    return FakeEvent(midi.MIDI_NOTEON, number, 0)


def unpack(message):
    return message & 0xFF, (message >> 8) & 0xFF, message >> 16


def hsb_messages(control_id, hsb, components=(0, 1, 2)):
    """The messages that set the given components of an HSB LED."""
    control = controls.BY_ID[control_id]
    status = midi.MIDI_CONTROLCHANGE if control.msg == controls.CC else midi.MIDI_NOTEON
    return {(status + i, control.number, hsb[i]) for i in components}


RED = (0, 127, 127)
PAD_IDS = [c.id for c in controls.ALL_CONTROLS if c.kind == controls.PAD]
GROUP_IDS = ["GROUP_" + letter for letter in "ABCDEFGH"]


class ScriptTestCase(unittest.TestCase):
    """Loads the script fresh for each test, with FL's state reset."""

    def setUp(self):
        script.controller = MaschineMk2()
        self.controller = script.controller
        device.reset()
        channels.selected = 0
        channels.colors = {0: 0xFF0000}
        plugins.names = {}
        plugins.pads = {}
        log.DEBUG_FPC_COLORS = False
        ui.focused = None
        ui.snap_mode = midi.Snap_None
        transport.reset()
        general.ppq = 96
        general.ppb = 384
        self.log = io.StringIO()
        self._redirect = contextlib.redirect_stdout(self.log)
        self._redirect.__enter__()
        script.OnInit()

    def tearDown(self):
        self._redirect.__exit__(None, None, None)

    def send(self, event):
        device.reset()
        script.OnMidiMsg(event)
        return event


class ScaffoldTest(ScriptTestCase):
    def test_init_lights_pads_and_groups_in_channel_colour(self):
        expected = set()
        for pad_id in PAD_IDS:
            expected |= hsb_messages(pad_id, RED)
        expected |= hsb_messages("GROUP_D", RED)  # the script starts on Group D
        for group_id in GROUP_IDS[:3] + GROUP_IDS[4:]:
            expected |= hsb_messages(group_id, (0, 127, renderer.DIM_BRIGHTNESS))
        for control in controls.LED_CONTROLS:
            if control.led == controls.MONO:
                expected.add((midi.MIDI_CONTROLCHANGE, control.number, 0))
        sent = [unpack(m) for m in device.sent]
        self.assertEqual(len(sent), len(expected))
        self.assertEqual(set(sent), expected)

    def test_group_button_moves_the_bright_group(self):
        self.assertTrue(self.send(cc(controls.BY_ID["GROUP_B"].number)).handled)
        self.assertEqual(self.controller.state.pad_group, 1)
        # Group B was pressed, so all of it is resent; only Group A's brightness changes.
        expected = hsb_messages("GROUP_B", RED) | hsb_messages("GROUP_D", (0, 127, renderer.DIM_BRIGHTNESS), (2,))
        sent = [unpack(m) for m in device.sent]
        self.assertEqual(len(sent), len(expected))
        self.assertEqual(set(sent), expected)

    def test_channel_colour_change_sends_only_changed_components(self):
        channels.colors[0] = 0x00FF00
        device.reset()
        script.OnRefresh(0)
        green_hue = colors.rgb_to_hsb(0x00FF00)[0]
        sent = [unpack(m) for m in device.sent]
        self.assertEqual(len(sent), len(PAD_IDS) + len(GROUP_IDS))
        self.assertTrue(all(status & 0x0F == 0 and value == green_hue for status, _, value in sent))

    def test_no_selected_channel_shows_white(self):
        frame = renderer.render(self.controller.state, FlSnapshot(channel_color=None))
        self.assertEqual(frame["PAD_1"], colors.WHITE)

    def test_rgb_to_hsb(self):
        self.assertEqual(colors.rgb_to_hsb(0xFF0000), (0, 127, 127))
        self.assertEqual(colors.rgb_to_hsb(0x00FF00), (42, 127, 127))
        self.assertEqual(colors.rgb_to_hsb(0x0000FF), (85, 127, 127))
        self.assertEqual(colors.rgb_to_hsb(0xFFFFFF), (0, 0, 127))
        self.assertEqual(colors.rgb_to_hsb(0x000000), (0, 0, 0))
        self.assertEqual(colors.rgb_to_hsb(0x808080), (0, 0, 64))
        self.assertEqual(colors.rgb_to_hsb(-0xFF0100), (42, 127, 127))  # high bits ignored

    def test_f5_toggles_shift_and_its_led(self):
        f5 = controls.BY_ID["F5"].number

        self.assertTrue(self.send(cc(f5)).handled)
        self.assertTrue(self.controller.state.shift)
        self.assertEqual([unpack(m) for m in device.sent], [(midi.MIDI_CONTROLCHANGE, f5, 127)])

        self.send(cc(f5))
        self.assertFalse(self.controller.state.shift)
        self.assertEqual([unpack(m) for m in device.sent], [(midi.MIDI_CONTROLCHANGE, f5, 0)])

    def test_pressed_button_led_is_reasserted(self):
        # A toggle button lights itself on the hardware, so the script resends "off".
        mute = controls.BY_ID["MUTE"].number
        self.send(cc(mute))
        self.assertEqual([unpack(m) for m in device.sent], [(midi.MIDI_CONTROLCHANGE, mute, 0)])

    def test_pads_pass_through_to_fl_at_group_d_notes(self):
        pad_1 = controls.BY_ID["PAD_1"].number
        event = self.send(note_on(pad_1))
        self.assertFalse(event.handled)
        self.assertEqual(event.data1, 48)
        event = self.send(note_off(pad_1))
        self.assertFalse(event.handled)
        self.assertEqual(event.data1, 48)
        self.assertEqual(self.send(note_on(controls.BY_ID["PAD_13"].number)).data1, 60)  # middle C

    def test_groups_cover_every_note_once(self):
        played = [notes.pad_note(group, pad) for group in range(8) for pad in range(16)]
        self.assertEqual(sorted(played), list(range(128)))
        self.assertEqual(notes.pad_note(0, notes.PAD_INDEX["PAD_1"]), 0)
        self.assertEqual(notes.pad_note(7, notes.PAD_INDEX["PAD_16"]), 127)

    def test_group_button_changes_pad_notes(self):
        self.send(cc(controls.BY_ID["GROUP_A"].number))
        self.assertEqual(self.send(note_on(controls.BY_ID["PAD_16"].number)).data1, 15)

    def test_note_off_uses_the_note_sent_at_press(self):
        pad_1 = controls.BY_ID["PAD_1"].number
        self.send(note_on(pad_1))
        self.send(cc(controls.BY_ID["GROUP_E"].number))  # group changes while the pad is held
        event = self.send(note_off(pad_1))
        self.assertFalse(event.handled)
        self.assertEqual(event.data1, 48)

    def test_aftertouch_follows_the_sounding_note(self):
        pad_1 = controls.BY_ID["PAD_1"].number
        self.send(note_on(pad_1))
        self.send(cc(controls.BY_ID["F5"].number))  # shift on while the pad is held
        event = self.send(FakeEvent(midi.MIDI_KEYAFTERTOUCH, pad_1, 90))
        self.assertFalse(event.handled)
        self.assertEqual(event.data1, 48)

    def test_shifted_pad_is_handled_by_the_script(self):
        self.controller.state.shift = True
        pad = controls.BY_ID["PAD_1"].number
        self.assertTrue(self.send(note_on(pad)).handled)
        self.assertIn('SHIFT+PAD_1 "undo"', self.log.getvalue())

    def test_release_goes_to_the_handler_that_took_the_press(self):
        pad = controls.BY_ID["PAD_1"].number
        self.send(note_on(pad))
        self.send(cc(controls.BY_ID["F5"].number))  # shift on while the pad is held
        self.assertFalse(self.send(note_off(pad)).handled)  # note-off still reaches FL

    def test_unimplemented_controls_log(self):
        self.assertTrue(self.send(cc(controls.BY_ID["ENTER"].number)).handled)
        self.assertIn('unimplemented: ENTER "enter"', self.log.getvalue())

    def test_unbound_knob_passes_through(self):
        self.assertFalse(self.send(cc(controls.BY_ID["E1"].number, 64)).handled)

    def test_unmapped_message_is_left_for_fl(self):
        self.assertFalse(self.send(cc(0)).handled)

    def test_every_control_in_both_layers_runs_without_error(self):
        for shift in (False, True):
            self.controller.state.shift = shift
            for control in controls.ALL_CONTROLS:
                if control.msg == controls.CC:
                    self.send(cc(control.number))
                else:
                    self.send(note_on(control.number))
                    self.send(note_off(control.number))
                self.controller.state.shift = shift  # undo F5's toggle
        self.assertNotIn("handler failed", self.log.getvalue())

    def test_refresh_without_changes_sends_nothing(self):
        device.reset()
        script.OnRefresh(0xFFFF)
        self.assertEqual(device.sent, [])

    def test_deinit_turns_lit_leds_off(self):
        self.send(cc(controls.BY_ID["F5"].number))
        device.reset()
        script.OnDeInit()
        sent = [unpack(m) for m in device.sent]
        self.assertTrue(all(value == 0 for _, _, value in sent))
        lit = {data1 for _, data1, _ in sent}
        self.assertIn(controls.BY_ID["F5"].number, lit)
        self.assertIn(controls.BY_ID["PAD_1"].number, lit)
        self.assertIn(controls.BY_ID["GROUP_H"].number, lit)


WINDOW_BUTTONS = {
    "BROWSE": midi.widBrowser,
    "F1": midi.widChannelRack,
    "F2": midi.widPianoRoll,
    "F3": midi.widPlaylist,
    "F4": midi.widMixer,
}


class WindowButtonsTest(ScriptTestCase):
    def lit_window_buttons(self):
        return [button for button in WINDOW_BUTTONS if self.controller.leds._sent[button]]

    def test_press_focuses_and_press_again_hides(self):
        f1 = controls.BY_ID["F1"].number
        self.send(cc(f1))
        self.assertEqual(ui.focused, midi.widChannelRack)
        self.assertEqual([unpack(m) for m in device.sent], [(midi.MIDI_CONTROLCHANGE, f1, 127)])
        self.send(cc(f1))
        self.assertIsNone(ui.focused)
        self.assertEqual([unpack(m) for m in device.sent], [(midi.MIDI_CONTROLCHANGE, f1, 0)])

    def test_each_button_focuses_its_window_and_lights_alone(self):
        for button, window in WINDOW_BUTTONS.items():
            with self.subTest(button=button):
                self.send(cc(controls.BY_ID[button].number))
                self.assertEqual(ui.focused, window)
                self.assertEqual(self.lit_window_buttons(), [button])

    def test_focus_changed_elsewhere_moves_the_light(self):
        self.send(cc(controls.BY_ID["F1"].number))
        ui.focused = midi.widMixer  # e.g. clicked with the mouse
        script.OnRefresh(0)
        self.assertEqual(self.lit_window_buttons(), ["F4"])

    def test_works_the_same_with_shift_on(self):
        self.controller.state.shift = True
        self.send(cc(controls.BY_ID["BROWSE"].number))
        self.assertEqual(ui.focused, midi.widBrowser)


class TransportTest(ScriptTestCase):
    def press(self, control_id):
        del transport.calls[:]
        return self.send(cc(controls.BY_ID[control_id].number))

    def led(self, control_id):
        return self.controller.leds._sent[control_id]

    def test_play_toggles_playback_and_its_led(self):
        self.press("PLAY")
        self.assertEqual(transport.calls, [("start",)])
        self.assertTrue(self.led("PLAY"))
        self.press("PLAY")
        self.assertFalse(transport.playing)
        self.assertFalse(self.led("PLAY"))

    def test_rec_toggles_recording_and_its_led(self):
        self.press("REC")
        self.assertEqual(transport.calls, [("record",)])
        self.assertTrue(self.led("REC"))

    def test_restart_stops_rewinds_and_plays(self):
        transport.song_pos = 1000
        self.press("RESTART")
        self.assertEqual(transport.calls, [("stop",), ("setSongPos", 0, -1), ("start",)])
        self.assertTrue(transport.playing)

    def test_shift_play_and_rec_toggle_metronome_and_count_in(self):
        self.controller.state.shift = True
        self.press("PLAY")
        self.assertEqual(transport.calls, [("globalTransport", midi.FPT_Metronome, 1)])
        self.assertFalse(transport.playing)
        self.press("REC")
        self.assertEqual(transport.calls, [("globalTransport", midi.FPT_CountDown, 1)])

    def test_snap_ticks(self):
        cases = [
            (midi.Snap_Bar, 384), (midi.Snap_Beat, 96), (midi.Snap_HalfBeat, 48),
            (midi.Snap_Step, 24), (midi.Snap_SixthStep, 4), (midi.Snap_None, 24),
            (midi.Snap_Line, 24), (midi.Snap_Cell, 24),
        ]
        for mode, ticks in cases:
            with self.subTest(mode=mode):
                self.assertEqual(transport_controls.snap_ticks(mode, 96, 384), ticks)
        self.assertEqual(transport_controls.snap_ticks(midi.Snap_FourthStep, 72, 288), 4)
        self.assertEqual(transport_controls.snap_ticks(midi.Snap_Bar, 96, 288), 288)  # 3/4

    def test_step_buttons_move_to_bar_lines(self):
        ui.snap_mode = midi.Snap_Bar
        transport.song_pos = 500
        self.press("STEP_RIGHT")
        self.assertEqual(transport.song_pos, 768)
        transport.song_pos = 500
        self.press("STEP_LEFT")
        self.assertEqual(transport.song_pos, 384)  # back to the current bar's line first
        self.press("STEP_LEFT")
        self.assertEqual(transport.song_pos, 0)
        self.press("STEP_LEFT")
        self.assertEqual(transport.song_pos, 0)  # never negative
        self.assertEqual(transport.calls, [("setSongPos", 0, midi.SONGLENGTH_ABSTICKS)])

    def test_step_buttons_move_to_step_lines(self):
        ui.snap_mode = midi.Snap_Step
        transport.song_pos = 20
        self.press("STEP_RIGHT")
        self.assertEqual(transport.song_pos, 24)
        transport.song_pos = 20
        self.press("STEP_LEFT")
        self.assertEqual(transport.song_pos, 0)

    def test_playback_started_elsewhere_lights_play(self):
        transport.playing = True
        script.OnRefresh(0)
        self.assertTrue(self.led("PLAY"))

    def test_grid_and_erase_are_unimplemented(self):
        self.press("GRID")
        self.press("ERASE")
        self.assertIn("unimplemented: GRID", self.log.getvalue())
        self.assertIn("unimplemented: ERASE", self.log.getvalue())


# FPC on channel 1: bank A pads are red with notes 36-51 and pad 2 empty; bank B pads are blue
# with notes 52-67.
FPC_CHANNEL = 1
FPC_PADS = [(36 + i, 0xFF0000 if i < 16 else 0x0000FF, i == 1) for i in range(32)]


class FpcModeTest(ScriptTestCase):
    def select_fpc(self):
        plugins.names[FPC_CHANNEL] = "FPC"
        plugins.pads[FPC_CHANNEL] = FPC_PADS
        channels.selected = FPC_CHANNEL
        channels.colors[FPC_CHANNEL] = 0x00FF00
        device.reset()
        script.OnRefresh(0)

    def select_channel(self, channel):
        channels.selected = channel
        device.reset()
        script.OnRefresh(0)

    def pad_leds(self):
        return {pad_id: self.controller.leds._sent[pad_id] for pad_id in PAD_IDS}

    def test_selecting_fpc_jumps_to_group_c_once(self):
        self.select_fpc()
        self.assertEqual(self.controller.state.pad_group, 4)
        self.send(cc(controls.BY_ID["GROUP_F"].number))
        script.OnRefresh(0)
        self.assertEqual(self.controller.state.pad_group, 5)  # no jump back while FPC stays selected
        self.select_channel(0)
        self.select_channel(FPC_CHANNEL)
        self.assertEqual(self.controller.state.pad_group, 4)  # selecting FPC again jumps again

    def test_group_e_plays_bank_a_and_group_f_bank_b(self):
        self.select_fpc()
        pad_1 = controls.BY_ID["PAD_1"].number
        self.assertEqual(self.send(note_on(pad_1)).data1, 36)
        self.send(note_off(pad_1))
        self.send(cc(controls.BY_ID["GROUP_F"].number))
        self.assertEqual(self.send(note_on(pad_1)).data1, 52)

    def test_empty_fpc_pad_is_silent_and_dark(self):
        self.select_fpc()
        event = self.send(note_on(controls.BY_ID["PAD_2"].number))
        self.assertTrue(event.handled)
        self.assertTrue(self.send(note_off(controls.BY_ID["PAD_2"].number)).handled)
        self.assertEqual(self.pad_leds()["PAD_2"], colors.OFF)

    def test_pads_show_fpc_colours(self):
        self.select_fpc()
        leds = self.pad_leds()
        self.assertEqual(leds["PAD_1"], (0, 127, 127))  # red
        self.send(cc(controls.BY_ID["GROUP_F"].number))
        self.assertEqual(self.pad_leds()["PAD_1"], (85, 127, 127))  # blue

    def test_other_groups_are_silent_and_dark(self):
        self.select_fpc()
        self.send(cc(controls.BY_ID["GROUP_A"].number))
        self.assertTrue(self.send(note_on(controls.BY_ID["PAD_1"].number)).handled)
        self.assertTrue(all(value == colors.OFF for value in self.pad_leds().values()))

    def test_only_fpc_groups_are_lit(self):
        self.select_fpc()
        sent = self.controller.leds._sent
        green = colors.rgb_to_hsb(0x00FF00)
        self.assertEqual(sent["GROUP_E"], green)
        self.assertEqual(sent["GROUP_F"], colors.with_brightness(green, renderer.DIM_BRIGHTNESS))
        for letter in "ABCDGH":
            self.assertEqual(sent["GROUP_" + letter], colors.OFF)

    def test_note_off_after_leaving_fpc_uses_sounding_note(self):
        self.select_fpc()
        pad_1 = controls.BY_ID["PAD_1"].number
        self.send(note_on(pad_1))
        self.select_channel(0)
        event = self.send(note_off(pad_1))
        self.assertFalse(event.handled)
        self.assertEqual(event.data1, 36)

    def test_leaving_fpc_restores_chromatic_layout(self):
        self.select_fpc()
        self.select_channel(0)
        self.assertEqual(self.send(note_on(controls.BY_ID["PAD_1"].number)).data1, 64)  # Group E, chromatic
        self.assertEqual(self.pad_leds()["PAD_1"], RED)


if __name__ == "__main__":
    unittest.main()
