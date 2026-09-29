"""
Drives the entry script end to end with stand-ins for FL Studio's modules.
Run from the FL Complete folder: python3 -m unittest discover -s tests -v
"""

import contextlib
import gc
import io
import os
import tempfile
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path[:0] = [os.path.join(HERE, "fl_stubs"), ROOT]

import channels  # noqa: E402  (the stub)
import device  # noqa: E402  (the stub)
import general  # noqa: E402  (the stub)
import mixer  # noqa: E402  (the stub)
import patterns  # noqa: E402  (the stub)
import plugins  # noqa: E402  (the stub)
import transport  # noqa: E402  (the stub)
import ui  # noqa: E402  (the stub)
import midi  # noqa: E402

import device_FLC_MaschineMK2 as script  # noqa: E402
from flc_maschine import bindings, controls, diagnostics, log, notes  # noqa: E402
from flc_maschine.state import NEW, SHIFT  # noqa: E402
from flc_maschine.controller import MaschineMk2  # noqa: E402
from flc_maschine.rendering import colors, renderer  # noqa: E402
from flc_maschine.handlers import pads, transport_controls, ui_commands  # noqa: E402
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
        ui.in_popup_menu = False
        ui.hints = []
        channels.shown_forms = []
        channels.quantized = []
        channels.pitch = {}
        channels.pitch_range = {}
        channels.pitch_calls = []
        channels.muted = set()
        channels.soloed = None
        channels.count = 8
        channels.selection = set()
        transport.reset()
        del patterns.calls[:]
        patterns.current = 1
        patterns.selected = set()
        del general.calls[:]
        general.safe = True
        diagnostics.ENABLED = False
        mixer.track_volume = {0: 0.8}
        mixer.track_number = 0
        mixer.track_count = 10
        mixer.selected_tracks = set()
        general.ppq = 96
        general.ppb = 384
        self.log = io.StringIO()
        self._redirect = contextlib.redirect_stdout(self.log)
        self._redirect.__enter__()
        script.OnInit()

    def tearDown(self):
        self._redirect.__exit__(None, None, None)

    def send(self, event):
        """Send a MIDI event, then run one OnIdle so any LED changes are rendered."""
        device.reset()
        script.OnMidiMsg(event)
        script.OnIdle()
        return event

    def refresh(self, flags=0):
        """An FL refresh, then one OnIdle to render it."""
        script.OnRefresh(flags)
        script.OnIdle()


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
        self.refresh()
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

    def test_f8_toggles_shift_and_its_led(self):
        f8 = controls.BY_ID["F8"].number

        self.assertTrue(self.send(cc(f8)).handled)
        self.assertEqual(self.controller.state.mode, SHIFT)
        self.assertIn((midi.MIDI_CONTROLCHANGE, f8, 127), [unpack(m) for m in device.sent])

        self.send(cc(f8))
        self.assertIsNone(self.controller.state.mode)
        self.assertIn((midi.MIDI_CONTROLCHANGE, f8, 0), [unpack(m) for m in device.sent])

    def test_pressed_button_led_is_reasserted(self):
        # A toggle button lights itself on the hardware, so the script resends "off".
        erase = controls.BY_ID["ERASE"].number
        self.send(cc(erase))
        self.assertEqual([unpack(m) for m in device.sent], [(midi.MIDI_CONTROLCHANGE, erase, 0)])

    def test_f5_and_f6_send_menu_and_escape(self):
        for button, command in (("F5", midi.FPT_Menu), ("F6", midi.FPT_Escape)):
            with self.subTest(button=button):
                del transport.calls[:]
                self.send(cc(controls.BY_ID[button].number))
                self.assertEqual(transport.calls, [("globalTransport", command, 1)])
                self.assertIsNone(self.controller.state.mode)
                self.assertFalse(self.controller.leds._sent[button])

    def test_f5_opens_the_item_menu_in_browser_and_piano_roll(self):
        cases = [
            (midi.widBrowser, midi.FPT_ItemMenu),
            (midi.widPianoRoll, midi.FPT_ItemMenu),
            (midi.widMixer, midi.FPT_Menu),
            (midi.widChannelRack, midi.FPT_Menu),
            (midi.widPlaylist, midi.FPT_Menu),
        ]
        for window, command in cases:
            with self.subTest(window=window):
                ui.focused = window
                del transport.calls[:]
                self.send(cc(controls.BY_ID["F5"].number))
                self.assertEqual(transport.calls, [("globalTransport", command, 1)])

    def test_pads_pass_through_to_fl_at_group_d_notes(self):
        pad_1 = controls.BY_ID["PAD_1"].number
        event = self.send(note_on(pad_1))
        self.assertFalse(event.handled)
        self.assertEqual(event.data1, 48)
        event = self.send(note_off(pad_1))
        self.assertFalse(event.handled)
        self.assertEqual(event.data1, 48)
        self.assertEqual(self.send(note_on(controls.BY_ID["PAD_13"].number)).data1, 60)  # middle C

    def test_pad_mode_toggles_fixed_velocity_and_its_led(self):
        self.send(cc(controls.BY_ID["PAD_MODE"].number))
        self.assertTrue(self.controller.state.fixed_velocity)
        self.assertTrue(self.controller.leds._sent["PAD_MODE"])
        self.send(cc(controls.BY_ID["PAD_MODE"].number))
        self.assertFalse(self.controller.state.fixed_velocity)
        self.assertFalse(self.controller.leds._sent["PAD_MODE"])

    def test_fixed_velocity_plays_pads_at_full_velocity(self):
        pad_1 = controls.BY_ID["PAD_1"].number
        self.assertEqual(self.send(note_on(pad_1, 40)).data2, 40)  # off: real velocity
        self.send(note_off(pad_1))
        self.send(cc(controls.BY_ID["PAD_MODE"].number))
        event = self.send(note_on(pad_1, 40))
        self.assertFalse(event.handled)
        self.assertEqual((event.data1, event.data2), (48, 127))  # still translated
        event = self.send(note_off(pad_1))
        self.assertEqual((event.data1, event.data2), (48, 0))  # note-off untouched

    def test_fixed_velocity_leaves_aftertouch_alone(self):
        pad_1 = controls.BY_ID["PAD_1"].number
        self.send(cc(controls.BY_ID["PAD_MODE"].number))
        self.send(note_on(pad_1, 40))
        event = self.send(FakeEvent(midi.MIDI_KEYAFTERTOUCH, pad_1, 55))
        self.assertEqual(event.data2, 55)

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
        self.send(cc(controls.BY_ID["F8"].number))  # shift on while the pad is held
        event = self.send(FakeEvent(midi.MIDI_KEYAFTERTOUCH, pad_1, 90))
        self.assertFalse(event.handled)
        self.assertEqual(event.data1, 48)

    def test_shifted_pad_is_handled_by_the_script(self):
        self.controller.state.mode = SHIFT
        pad = controls.BY_ID["PAD_4"].number
        self.assertTrue(self.send(note_on(pad)).handled)
        self.assertIn('SHIFT+PAD_4 "split"', self.log.getvalue())

    def test_release_goes_to_the_handler_that_took_the_press(self):
        pad = controls.BY_ID["PAD_1"].number
        self.send(note_on(pad))
        self.send(cc(controls.BY_ID["F8"].number))  # shift on while the pad is held
        self.assertFalse(self.send(note_off(pad)).handled)  # note-off still reaches FL

    def test_unimplemented_controls_log(self):
        self.assertTrue(self.send(cc(controls.BY_ID["NOTE_REPEAT"].number)).handled)
        self.assertIn("unimplemented: NOTE_REPEAT", self.log.getvalue())

    def test_master_left_right_and_enter_send_their_commands(self):
        for button, command in (("MASTER_LEFT", midi.FPT_Left), ("MASTER_RIGHT", midi.FPT_Right), ("ENTER", midi.FPT_Enter)):
            with self.subTest(button=button):
                del transport.calls[:]
                self.send(cc(controls.BY_ID[button].number))
                self.assertEqual(transport.calls, [("globalTransport", command, 1)])

    def test_enter_opens_the_selected_channel_plugin_in_the_channel_rack(self):
        ui.focused = midi.widChannelRack
        channels.selected = 2
        del transport.calls[:]
        self.send(cc(controls.BY_ID["ENTER"].number))
        self.assertEqual(channels.shown_forms, [(2, 1)])
        self.assertEqual(transport.calls, [])

    def test_enter_in_the_channel_rack_without_a_selection_does_nothing(self):
        ui.focused = midi.widChannelRack
        channels.selected = -1
        del transport.calls[:]
        self.send(cc(controls.BY_ID["ENTER"].number))
        self.assertEqual(channels.shown_forms, [])
        self.assertEqual(transport.calls, [])

    def test_enter_picks_a_popup_menu_item_and_works_elsewhere(self):
        for focused, in_menu in ((midi.widChannelRack, True), (midi.widPlaylist, False)):
            with self.subTest(focused=focused, in_menu=in_menu):
                ui.focused = focused
                ui.in_popup_menu = in_menu
                del transport.calls[:]
                self.send(cc(controls.BY_ID["ENTER"].number))
                self.assertEqual(transport.calls, [("globalTransport", midi.FPT_Enter, 1)])
                self.assertEqual(channels.shown_forms, [])

    def test_unbound_knob_passes_through(self):
        self.assertFalse(self.send(cc(controls.BY_ID["E1"].number, 64)).handled)

    def test_unmapped_message_is_left_for_fl(self):
        self.assertFalse(self.send(cc(0)).handled)

    def test_every_control_in_every_layer_runs_without_error(self):
        for mode in (None, SHIFT, NEW):
            self.controller.state.mode = mode
            for control in controls.ALL_CONTROLS:
                if control.msg == controls.CC:
                    self.send(cc(control.number))
                else:
                    self.send(note_on(control.number))
                    self.send(note_off(control.number))
                self.controller.state.mode = mode  # undo mode toggles and one-shot New functions
        self.assertNotIn("handler failed", self.log.getvalue())

    def test_refresh_without_changes_sends_nothing(self):
        device.reset()
        script.OnRefresh(0xFFFF)
        self.assertEqual(device.sent, [])

    def test_deinit_turns_lit_leds_off(self):
        self.send(cc(controls.BY_ID["F8"].number))
        lit = {control_id for control_id, value in self.controller.leds._sent.items()
               if value not in (False, colors.OFF)}
        self.assertIn("F8", lit)
        self.assertIn("PAD_1", lit)
        device.reset()
        script.OnDeInit()
        sent = [unpack(m) for m in device.sent]
        self.assertTrue(all(value == 0 for _, _, value in sent))
        self.assertEqual({data1 for _, data1, _ in sent}, {controls.BY_ID[c].number for c in lit})


WINDOW_BUTTONS = {
    "BROWSE": midi.widBrowser,
    "F1": midi.widChannelRack,
    "F2": midi.widPianoRoll,
    "F3": midi.widPlaylist,
    "F4": midi.widMixer,
}


class SoloMuteTest(ScriptTestCase):
    def press(self, button_id):
        self.send(cc(controls.BY_ID[button_id].number))

    def led(self, control_id):
        return self.controller.leds._sent.get(control_id)

    def select(self, channel):
        channels.selected = channel
        self.refresh()

    def test_mute_toggles_the_selected_channel(self):
        self.press("MUTE")
        self.assertEqual(channels.muted, {0})
        self.assertTrue(self.led("MUTE"))
        self.press("MUTE")
        self.assertEqual(channels.muted, set())
        self.assertFalse(self.led("MUTE"))

    def test_solo_toggles_the_selected_channel(self):
        channels.selected = 2
        self.press("SOLO")
        self.assertEqual(channels.soloed, 2)
        self.assertTrue(self.led("SOLO"))
        self.press("SOLO")
        self.assertIsNone(channels.soloed)
        self.assertFalse(self.led("SOLO"))

    def test_nothing_without_a_selected_channel(self):
        channels.selected = -1
        self.press("MUTE")
        self.press("SOLO")
        self.assertEqual(channels.muted, set())
        self.assertIsNone(channels.soloed)
        self.assertFalse(self.led("MUTE"))
        self.assertFalse(self.led("SOLO"))

    def test_leds_follow_the_selection(self):
        channels.muted = {1}
        self.select(1)
        self.assertTrue(self.led("MUTE"))
        self.select(0)
        self.assertFalse(self.led("MUTE"))

    def test_leds_follow_changes_made_in_fl(self):
        channels.soloed = 0
        self.refresh()
        self.assertTrue(self.led("SOLO"))
        channels.soloed = None
        self.refresh()
        self.assertFalse(self.led("SOLO"))


class EncoderDragSelectTest(ScriptTestCase):
    def hold(self):
        self.send(cc(controls.BY_ID["ENCODER_PUSH"].number, 127))

    def release(self):
        self.send(cc(controls.BY_ID["ENCODER_PUSH"].number, 0))

    def turn(self, delta, times=1):
        for _ in range(times):
            self.send(cc(controls.BY_ID["ENCODER"].number, delta & 0x7F))

    def test_channel_rack_drag_grows_and_shrinks_from_the_selected_channel(self):
        ui.focused = midi.widChannelRack
        channels.selected = 2
        channels.selection = {2, 6}
        self.hold()
        del transport.calls[:]
        self.turn(+1, times=2)
        self.assertEqual(channels.selection, {2, 3, 4})
        self.assertEqual(ui.hints[-1], "Select: channels 3-5")
        self.turn(-1, times=3)  # back past the anchor
        self.assertEqual(channels.selection, {1, 2})
        self.assertEqual(ui.hints[-1], "Select: channels 2-3")
        self.release()
        self.assertEqual(transport.calls, [])  # no navigation, and no click on release
        self.assertEqual(channels.selection, {1, 2})

    def test_channel_range_stops_at_the_first_and_last_channels(self):
        ui.focused = midi.widChannelRack
        channels.selected = 1
        self.hold()
        self.turn(-1, times=3)
        self.assertEqual(channels.selection, {0, 1})
        self.turn(+1, times=20)
        self.assertEqual(channels.selection, set(range(1, channels.count)))

    def test_mixer_drag_selects_tracks(self):
        ui.focused = midi.widMixer
        mixer.track_number = 3
        mixer.selected_tracks = {3, 7}
        self.hold()
        self.turn(+1, times=2)
        self.assertEqual(mixer.selected_tracks, {3, 4, 5})
        self.assertEqual(ui.hints[-1], "Select: mixer tracks 3-5")
        self.turn(-1, times=3)
        self.assertEqual(mixer.selected_tracks, {2, 3})
        self.turn(+1, times=20)  # stops before the "Current" track
        self.assertEqual(mixer.selected_tracks, set(range(3, mixer.track_count - 1)))
        self.release()
        self.assertNotIn(("globalTransport", midi.FPT_Menu, 1), transport.calls)

    def test_click_acts_on_release(self):
        ui.focused = midi.widChannelRack
        del transport.calls[:]
        self.hold()
        self.assertEqual(transport.calls, [])
        self.release()
        self.assertEqual(transport.calls, [("globalTransport", midi.FPT_ItemMenu, 1)])

    def test_hold_and_turn_elsewhere_navigates_without_clicking(self):
        ui.focused = midi.widPlaylist
        self.hold()
        del transport.calls[:]
        self.turn(+1)
        self.release()
        self.assertEqual(transport.calls, [("globalTransport", midi.FPT_Down, 1)])

    def test_open_popup_menu_is_navigated_not_selected(self):
        ui.focused = midi.widChannelRack
        ui.in_popup_menu = True
        channels.selection = {0}
        self.hold()
        del transport.calls[:]
        self.turn(+1)
        self.assertEqual(transport.calls, [("globalTransport", midi.FPT_Down, 1)])
        self.assertEqual(channels.selection, {0})

    def test_drag_takes_priority_over_an_override(self):
        ui.focused = midi.widChannelRack
        self.send(cc(controls.BY_ID["VOLUME"].number))
        self.hold()
        self.turn(+1)
        self.assertEqual(channels.selection, {0, 1})
        self.assertEqual(mixer.track_volume[0], 0.8)

    def test_plain_turn_still_navigates(self):
        ui.focused = midi.widChannelRack
        del transport.calls[:]
        self.turn(+1)
        self.assertEqual(transport.calls, [("globalTransport", midi.FPT_Down, 1)])
        self.assertEqual(channels.selection, set())


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
        self.refresh()
        self.assertEqual(self.lit_window_buttons(), ["F4"])

    def test_f1_to_f4_work_the_same_with_shift_on(self):
        # BROWSE has a shift function (plugin picker); F1-F4 don't, so they fall back to base.
        self.controller.state.mode = SHIFT
        self.send(cc(controls.BY_ID["F1"].number))
        self.assertEqual(ui.focused, midi.widChannelRack)


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
        self.controller.state.mode = SHIFT
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
        self.refresh()
        self.assertTrue(self.led("PLAY"))

    def test_scene_switches_between_pattern_and_song_mode(self):
        self.press("SCENE")
        self.assertEqual(transport.calls, [("setLoopMode",)])
        self.assertTrue(self.led("SCENE"))  # song mode
        self.assertIsNone(self.controller.state.encoder_mode)
        self.press("SCENE")
        self.assertFalse(self.led("SCENE"))  # pattern mode

    def test_song_mode_set_elsewhere_lights_scene(self):
        transport.loop_mode = 1
        self.refresh()
        self.assertTrue(self.led("SCENE"))

    def test_erase_is_unimplemented(self):
        self.press("ERASE")
        self.assertIn("unimplemented: ERASE", self.log.getvalue())


class EncoderTest(ScriptTestCase):
    def press(self, control_id):
        del transport.calls[:]
        return self.send(cc(controls.BY_ID[control_id].number))

    def turn(self, delta):
        del transport.calls[:]
        return self.send(cc(controls.BY_ID["ENCODER"].number, delta & 0x7F))  # two's complement

    def click(self):
        """Push and release the encoder (Gate mode: 127, then 0). The push acts on release."""
        del transport.calls[:]
        self.send(cc(controls.BY_ID["ENCODER_PUSH"].number, 127))
        self.send(cc(controls.BY_ID["ENCODER_PUSH"].number, 0))

    def lit_override_buttons(self):
        return [b for b in ("VOLUME", "SWING", "TEMPO") if self.controller.leds._sent[b]]

    def test_override_buttons_toggle_their_mode_and_led(self):
        self.press("VOLUME")
        self.assertEqual(self.controller.state.encoder_mode, "VOLUME")
        self.assertEqual(self.lit_override_buttons(), ["VOLUME"])
        self.press("VOLUME")
        self.assertIsNone(self.controller.state.encoder_mode)
        self.assertEqual(self.lit_override_buttons(), [])

    def test_pressing_another_override_switches_to_it(self):
        self.press("VOLUME")
        self.press("SWING")
        self.assertEqual(self.controller.state.encoder_mode, "SWING")
        self.assertEqual(self.lit_override_buttons(), ["SWING"])

    def test_volume_override_adjusts_master_volume(self):
        self.press("VOLUME")
        self.turn(1)
        self.assertAlmostEqual(mixer.track_volume[0], 0.85)
        self.turn(-1)
        self.turn(-1)
        self.assertAlmostEqual(mixer.track_volume[0], 0.75)
        for _ in range(10):
            self.turn(1)
        self.assertEqual(mixer.track_volume[0], 1.0)
        mixer.track_volume[0] = 0.02
        self.turn(-1)
        self.assertEqual(mixer.track_volume[0], 0.0)

    def test_navigate_override_jogs_between_windows(self):
        self.press("NAVIGATE")
        self.assertEqual(self.controller.state.encoder_mode, "NAVIGATE")
        self.assertTrue(self.controller.leds._sent["NAVIGATE"])
        ui.focused = midi.widMixer  # the override wins over focused-window navigation
        self.turn(1)
        self.assertEqual(transport.calls, [("globalTransport", midi.FPT_WindowJog, 1)])
        self.turn(-3)
        self.assertEqual(transport.calls, [("globalTransport", midi.FPT_WindowJog, -1)])

    def test_pattern_and_grid_overrides_jog(self):
        for button, command in (("PATTERN", midi.FPT_PatternJog), ("GRID", midi.FPT_SnapMode)):
            with self.subTest(button=button):
                self.press(button)
                self.assertEqual(self.controller.state.encoder_mode, button)
                self.assertTrue(self.controller.leds._sent[button])
                self.turn(1)
                self.assertEqual(transport.calls, [("globalTransport", command, 1)])
                self.turn(-3)
                self.assertEqual(transport.calls, [("globalTransport", command, -1)])
                self.press(button)  # off again

    def test_entering_shift_or_new_clears_the_override(self):
        for mode_button in ("F8", "F7"):
            with self.subTest(mode_button=mode_button):
                self.press("VOLUME")
                self.press(mode_button)
                self.assertIsNone(self.controller.state.encoder_mode)
                self.press(mode_button)  # mode off again: the override stays off
                self.assertIsNone(self.controller.state.encoder_mode)
                self.assertFalse(self.controller.leds._sent["VOLUME"])

    def test_swing_and_tempo_overrides_jog(self):
        self.press("SWING")
        self.turn(1)
        self.assertEqual(transport.calls, [("globalTransport", midi.FPT_ShuffleJog, 10)])
        self.press("TEMPO")
        self.turn(-1)
        self.assertEqual(transport.calls, [("globalTransport", midi.FPT_TempoJog, -10)])
        self.turn(3)
        self.assertEqual(transport.calls, [("globalTransport", midi.FPT_TempoJog, 30)])

    def jogs(self):
        return [call[1] for call in transport.calls if call[0] == "globalTransport"]

    def test_turn_with_nothing_focused_does_nothing(self):
        self.turn(1)
        self.assertEqual(transport.calls, [])
        self.assertEqual(mixer.track_volume[0], 0.8)

    def test_turn_navigates_the_focused_window(self):
        cases = [
            (midi.widMixer, midi.FPT_Left, midi.FPT_Right),
            (midi.widChannelRack, midi.FPT_Up, midi.FPT_Down),
            (midi.widPlaylist, midi.FPT_Up, midi.FPT_Down),
            (midi.widPianoRoll, midi.FPT_Up, midi.FPT_Down),
            (midi.widBrowser, midi.FPT_Up, midi.FPT_Down),
        ]
        for window, counter_clockwise, clockwise in cases:
            with self.subTest(window=window):
                ui.focused = window
                self.turn(1)
                self.assertEqual(self.jogs(), [clockwise])
                self.turn(-1)
                self.assertEqual(self.jogs(), [counter_clockwise])

    def test_popup_menu_takes_priority(self):
        ui.focused = midi.widMixer
        ui.in_popup_menu = True
        self.turn(1)
        self.assertEqual(self.jogs(), [midi.FPT_Down])
        self.click()
        self.assertEqual(self.jogs(), [midi.FPT_Enter])

    def test_override_takes_priority_over_navigation(self):
        ui.focused = midi.widMixer
        self.press("VOLUME")
        self.turn(1)
        self.assertEqual(transport.calls, [])
        self.assertAlmostEqual(mixer.track_volume[0], 0.85)

    def test_push_does_the_focused_windows_action(self):
        cases = [
            (midi.widBrowser, [midi.FPT_Enter]),
            (midi.widMixer, [midi.FPT_Menu]),
            (midi.widPlaylist, [midi.FPT_Menu]),
            (midi.widPianoRoll, [midi.FPT_Menu]),
        ]
        for window, expected in cases:
            with self.subTest(window=window):
                ui.focused = window
                self.click()
                self.assertEqual(self.jogs(), expected)

    def test_push_in_channel_rack_opens_the_item_menu(self):
        ui.focused = midi.widChannelRack
        self.click()
        self.assertEqual(self.jogs(), [midi.FPT_ItemMenu])

    def test_push_with_nothing_focused_does_nothing(self):
        self.click()
        self.assertEqual(transport.calls, [])


class ShiftModeTest(ScriptTestCase):
    def shift(self):
        self.send(cc(controls.BY_ID["F8"].number))

    def led(self, control_id):
        return self.controller.leds._sent[control_id]

    def test_shift_lights_only_controls_with_a_shift_function(self):
        ui.focused = midi.widChannelRack
        self.send(cc(controls.BY_ID["VOLUME"].number))  # override on
        self.assertTrue(self.led("F1"))
        self.assertTrue(self.led("VOLUME"))
        self.shift()
        for control_id in ("F8", "BROWSE", "PLAY", "REC"):
            self.assertTrue(self.led(control_id), control_id)
        # ALL's shift function (save) is still a placeholder, so it isn't highlighted.
        for control_id in ("F1", "MUTE", "RESTART", "VOLUME", "F5", "ALL"):
            self.assertFalse(self.led(control_id), control_id)

    def test_shift_browse_opens_plugin_picker(self):
        self.shift()
        del transport.calls[:]
        self.send(cc(controls.BY_ID["BROWSE"].number))
        self.assertEqual(transport.calls, [("globalTransport", midi.FPT_F8, 1)])
        self.assertIsNone(ui.focused)  # didn't toggle the browser
        self.assertEqual(self.controller.state.mode, SHIFT)  # shift stays on

    def test_shift_lights_implemented_pads_in_function_colours_and_darkens_groups(self):
        self.shift()
        expected = {"PAD_1": colors.ORANGE, "PAD_2": colors.ORANGE, "PAD_3": colors.ORANGE, "PAD_11": colors.CYAN, "PAD_12": colors.CYAN,
                    "PAD_5": colors.GREEN, "PAD_7": colors.BLUE, "PAD_8": colors.BLUE, "PAD_9": colors.RED, "PAD_10": colors.YELLOW,
                    "PAD_13": colors.PURPLE, "PAD_14": colors.PURPLE, "PAD_15": colors.PURPLE, "PAD_16": colors.PURPLE}
        for pad_id in PAD_IDS:
            self.assertEqual(self.led(pad_id), expected.get(pad_id, colors.OFF), pad_id)
        for group_id in GROUP_IDS:
            self.assertEqual(self.led(group_id), colors.OFF, group_id)

    def test_state_lights_return_when_shift_turns_off(self):
        ui.focused = midi.widChannelRack
        self.send(cc(controls.BY_ID["VOLUME"].number))
        self.shift()
        self.shift()
        self.assertTrue(self.led("F1"))
        self.assertFalse(self.led("VOLUME"))  # entering shift turned the override off
        self.assertFalse(self.led("F8"))
        self.assertEqual(self.led("GROUP_D"), RED)

    def test_shift_lights_pads_that_are_dark_in_fpc_mode(self):
        plugins.names[1] = "FPC"
        plugins.pads[1] = [(36 + i, 0xFF0000, False) for i in range(32)]
        channels.selected = 1
        self.refresh()
        self.send(cc(controls.BY_ID["GROUP_A"].number))  # not an FPC group: pads dark
        self.assertEqual(self.led("PAD_1"), colors.OFF)
        self.shift()
        self.assertEqual(self.led("PAD_1"), colors.ORANGE)
        self.assertEqual(self.led("PAD_4"), colors.OFF)

    def test_shift_controls_are_the_shift_layer(self):
        # Only real functions count: unimplemented(...) placeholders are left out.
        self.assertTrue({"PLAY", "REC", "PAD_1", "PAD_11"} <= bindings.MODE_CONTROLS[SHIFT])
        self.assertFalse({"ALL", "PAD_4"} & bindings.MODE_CONTROLS[SHIFT])
        self.assertTrue(bindings.MODE_CONTROLS[SHIFT] <= frozenset(bindings.LAYERS[SHIFT]))


class DuplicateTest(ScriptTestCase):
    def press(self):
        return self.send(cc(controls.BY_ID["DUPLICATE"].number))

    def test_clones_the_current_pattern(self):
        patterns.selected = {1}
        self.assertTrue(self.press().handled)
        self.assertEqual(patterns.calls, [("clonePattern",)])

    def test_selects_the_current_pattern_first(self):
        patterns.current = 3
        patterns.selected = {1}  # the Picker selection isn't the current pattern
        self.press()
        self.assertEqual(patterns.calls, [("jumpToPattern", 3), ("clonePattern",)])


class NewModeTest(ScriptTestCase):
    def press(self, control_id):
        del transport.calls[:]
        return self.send(cc(controls.BY_ID[control_id].number))

    def led(self, control_id):
        return self.controller.leds._sent[control_id]

    def test_f7_toggles_new_mode_and_its_led(self):
        self.press("F7")
        self.assertEqual(self.controller.state.mode, NEW)
        self.assertTrue(self.led("F7"))
        self.press("F7")
        self.assertIsNone(self.controller.state.mode)
        self.assertFalse(self.led("F7"))

    def test_new_and_shift_replace_each_other(self):
        self.press("F7")
        self.press("F8")
        self.assertEqual(self.controller.state.mode, SHIFT)
        self.assertFalse(self.led("F7"))
        self.press("F7")
        self.assertEqual(self.controller.state.mode, NEW)
        self.assertFalse(self.led("F8"))

    def test_new_browse_opens_the_add_menu(self):
        self.press("F7")
        self.press("BROWSE")
        self.assertEqual(transport.calls, [("globalTransport", midi.FPT_Menu, 1)])
        self.assertIsNone(self.controller.state.mode)
        del transport.calls[:]
        ui.in_popup_menu = True
        for _ in range(5):
            script.OnIdle()
        self.assertEqual(transport.calls, [("globalTransport", midi.FPT_Right, 1)] * 3)

    def test_queued_menu_commands_wait_for_the_menu_and_then_give_up(self):
        self.press("F7")
        self.press("BROWSE")
        del transport.calls[:]
        for _ in range(ui_commands.MENU_WAIT_TICKS):
            script.OnIdle()
        self.assertEqual(transport.calls, [])
        ui.in_popup_menu = True
        script.OnIdle()
        self.assertEqual(transport.calls, [])  # queue dropped: the menu never opened in time

    def test_new_pattern_starts_a_new_pattern_once(self):
        self.press("F7")
        self.press("PATTERN")
        self.assertEqual(patterns.calls, [("findFirstNextEmptyPat", midi.FFNEP_DontPromptName)])
        self.assertIsNone(self.controller.state.mode)

    def test_controls_without_a_new_function_act_normally_and_keep_new_mode(self):
        self.press("F7")
        self.press("PLAY")
        self.assertEqual(transport.calls, [("start",)])
        self.assertEqual(self.controller.state.mode, NEW)

    def test_new_mode_lights(self):
        self.press("F7")
        for control_id in ("F7", "BROWSE", "PATTERN"):
            self.assertTrue(self.led(control_id), control_id)
        for control_id in ("F8", "F1", "PLAY", "ALL"):
            self.assertFalse(self.led(control_id), control_id)
        for control_id in PAD_IDS + GROUP_IDS:
            self.assertEqual(self.led(control_id), colors.OFF, control_id)

    def test_new_mode_controls_are_the_new_layer(self):
        self.assertEqual(bindings.MODE_CONTROLS[NEW], frozenset(bindings.LAYERS[NEW]))


class ShiftPadTest(ScriptTestCase):
    def setUp(self):
        super().setUp()
        self.controller.state.mode = SHIFT
        del transport.calls[:]

    def hit(self, pad_id):
        event = self.send(note_on(controls.BY_ID[pad_id].number))
        self.send(note_off(controls.BY_ID[pad_id].number))
        return event

    def test_undo_and_redo(self):
        self.assertTrue(self.hit("PAD_1").handled)
        self.assertTrue(self.hit("PAD_2").handled)
        self.assertEqual(general.calls, ["undoUp", "undoDown"])

    def test_copy_and_paste(self):
        self.hit("PAD_11")
        self.hit("PAD_12")
        self.assertEqual(transport.calls, [("globalTransport", midi.FPT_Copy, 1), ("globalTransport", midi.FPT_Paste, 1)])

    def test_quantize_quantizes_the_selected_channel(self):
        channels.selected = 2
        self.hit("PAD_5")
        self.assertEqual(channels.quantized, [(2, 1)])
        channels.selected = -1
        self.hit("PAD_5")
        self.assertEqual(channels.quantized, [(2, 1)])  # no channel selected: nothing

    def test_compare_toggles_the_last_edit(self):
        self.hit("PAD_3")
        self.assertEqual(general.calls, ["undo"])

    def test_nudge_trims_tempo(self):
        self.hit("PAD_7")
        self.hit("PAD_8")
        self.assertEqual(transport.calls, [("globalTransport", midi.FPT_TempoJog, -1),
                                           ("globalTransport", midi.FPT_TempoJog, 1)])

    def test_clear_sends_delete(self):
        self.hit("PAD_9")
        self.assertEqual(transport.calls, [("globalTransport", midi.FPT_Delete, 1)])

    def test_clear_auto_sends_cut(self):
        self.hit("PAD_10")
        self.assertEqual(transport.calls, [("globalTransport", midi.FPT_Cut, 1)])
        self.assertEqual(self.controller.leds._sent["PAD_10"], colors.YELLOW)

    def test_quantize_50_stays_dark_and_silent(self):
        event = self.hit("PAD_6")
        self.assertTrue(event.handled)
        self.refresh()
        self.assertEqual(self.controller.leds._sent["PAD_6"], colors.OFF)

    def test_shift_pads_play_no_notes(self):
        for pad_id in ("PAD_1", "PAD_4"):  # implemented, and a placeholder
            with self.subTest(pad=pad_id):
                event = self.hit(pad_id)
                self.assertTrue(event.handled)
                self.assertEqual(event.data1, controls.BY_ID[pad_id].number)  # not translated to a note

    def test_placeholder_pads_stay_dark(self):
        self.refresh()
        self.assertEqual(self.controller.leds._sent["PAD_4"], colors.OFF)


class RenderSchedulingTest(ScriptTestCase):
    """FL may run OnMidiMsg and OnRefresh at the same time on different threads, so only OnIdle
    reads FL state and writes LEDs."""

    def count_renders(self):
        renders = []
        original = self.controller.render
        self.controller.render = lambda: (renders.append(1), original())
        return renders

    def test_midi_and_refresh_neither_read_fl_nor_write_leds(self):
        device.reset()
        plugins.names = None  # any plugin read would raise
        channels.colors[0] = 0x00FF00
        script.OnMidiMsg(cc(controls.BY_ID["F8"].number))
        script.OnRefresh(0)
        self.assertEqual(device.sent, [])
        self.assertTrue(self.controller.dirty)
        plugins.names = {}
        script.OnIdle()
        self.assertTrue(device.sent)
        self.assertFalse(self.controller.dirty)

    def test_many_events_render_once_per_idle(self):
        renders = self.count_renders()
        for _ in range(5):
            script.OnMidiMsg(cc(controls.BY_ID["F1"].number))
            script.OnRefresh(0x100)
        script.OnIdle()
        script.OnIdle()  # nothing new: no render
        self.assertEqual(len(renders), 1)

    def test_pressed_led_is_reasserted_on_the_next_idle(self):
        script.OnMidiMsg(cc(controls.BY_ID["ERASE"].number))
        self.assertIn("ERASE", self.controller.invalidated)
        device.reset()
        script.OnIdle()
        self.assertIn((midi.MIDI_CONTROLCHANGE, controls.BY_ID["ERASE"].number, 0), [unpack(m) for m in device.sent])
        self.assertEqual(self.controller.invalidated, set())

    def test_pads_use_the_last_snapshot_in_fpc_mode(self):
        plugins.names[1] = "FPC"
        plugins.pads[1] = [(36 + i, 0xFF0000, False) for i in range(32)]
        channels.selected = 1
        self.refresh()  # snapshot now holds FPC's pads; the pads jump to Group E
        plugins.names = None  # the pad press itself must not query FL
        event = note_on(controls.BY_ID["PAD_1"].number)
        script.OnMidiMsg(event)  # no idle: that render would legitimately read FL
        self.assertEqual(event.data1, 36)


class CrashMitigationTest(ScriptTestCase):
    def test_aftertouch_does_not_render(self):
        pad_1 = controls.BY_ID["PAD_1"].number
        self.send(note_on(pad_1))
        channels.colors[0] = 0x00FF00  # a render now would recolour the pads
        self.send(FakeEvent(midi.MIDI_KEYAFTERTOUCH, pad_1, 90))
        self.assertEqual(device.sent, [])

    def test_no_fl_reads_while_unsafe_then_catch_up_on_idle(self):
        general.safe = False
        plugins.names = None  # any plugin read would now raise
        channels.colors[0] = 0x00FF00
        device.reset()
        self.refresh()
        self.assertEqual(device.sent, [])
        self.assertTrue(self.controller.dirty)
        script.OnIdle()  # still unsafe: nothing
        self.assertEqual(device.sent, [])
        plugins.names = {}
        general.safe = True
        script.OnIdle()
        self.assertFalse(self.controller.dirty)
        self.assertTrue(device.sent)  # the pads were recoloured


class DiagnosticsTest(ScriptTestCase):
    def setUp(self):
        super().setUp()
        handle, self.path = tempfile.mkstemp(suffix=".log")
        os.close(handle)
        self.saved = (diagnostics.LOG_FILE, diagnostics.clock)
        diagnostics.LOG_FILE = self.path
        diagnostics.ENABLED = True
        self.now = 1000.0
        diagnostics.clock = lambda: self.now
        script.OnInit()

    def tearDown(self):
        gc.callbacks[:] = [cb for cb in gc.callbacks if cb is not diagnostics._gc_callback]
        diagnostics.LOG_FILE, diagnostics.clock = self.saved
        diagnostics.ENABLED = False
        os.remove(self.path)
        super().tearDown()

    def log_text(self):
        with open(self.path) as f:
            return f.read()

    def test_callbacks_and_controls_are_logged(self):
        script.OnMidiMsg(cc(controls.BY_ID["PLAY"].number))
        text = self.log_text()
        self.assertIn("FL Complete MK2 debug log", text)
        self.assertIn("> OnInit [t", text)
        self.assertIn("> OnMidiMsg [t", text)
        self.assertIn("midi PLAY press 127", text)
        self.assertIn("< OnMidiMsg", text)
        self.assertLess(text.index("midi PLAY press 127"), text.index("< OnMidiMsg"))

    def test_idle_is_counted_not_logged_and_stats_are_written(self):
        script.OnIdle()
        self.assertNotIn("> OnIdle", self.log_text())
        self.now += diagnostics.STATS_INTERVAL
        script.OnIdle()
        text = self.log_text()
        self.assertIn("stats: OnIdle=2", text)
        self.assertNotIn("stats failed", text)
        self.assertNotIn("memory", text)  # memory counters are off by default

    def test_memory_counters_when_switched_on(self):
        diagnostics.MEMORY_STATS = True
        try:
            self.now += diagnostics.STATS_INTERVAL
            script.OnIdle()
        finally:
            diagnostics.MEMORY_STATS = False
        text = self.log_text()
        stats_at = text.index("stats: ")
        memory_at = text.index("memory: blocks=")
        self.assertLess(stats_at, memory_at)  # the stats line is written first
        self.assertIn("gc_collections=", text)

    def test_garbage_collections_not_watched_by_default(self):
        self.assertFalse(any(cb is diagnostics._gc_callback for cb in gc.callbacks))

    def test_full_garbage_collections_are_logged(self):
        diagnostics.WATCH_GC = True
        self.addCleanup(setattr, diagnostics, "WATCH_GC", False)
        script.OnInit()
        self.assertEqual(sum(cb is diagnostics._gc_callback for cb in gc.callbacks), 1)
        script.OnInit()  # a reload must not register the callback twice
        self.assertEqual(sum(cb is diagnostics._gc_callback for cb in gc.callbacks), 1)
        gc.collect()  # a full (generation 2) collection
        text = self.log_text()
        self.assertIn("gc start gen2", text)
        self.assertIn("gc stop gen2: collected=", text)

    def test_exceptions_are_logged_and_reraised(self):
        def broken():
            raise ValueError("boom")
        with self.assertRaises(ValueError):
            diagnostics.run("OnRefresh", broken)
        text = self.log_text()
        self.assertIn("! exception in OnRefresh", text)
        self.assertIn("ValueError: boom", text)


class TransposeTest(ScriptTestCase):
    def shifted_hit(self, pad_id):
        self.controller.state.mode = SHIFT
        self.send(note_on(controls.BY_ID[pad_id].number))
        self.send(note_off(controls.BY_ID[pad_id].number))
        self.controller.state.mode = None

    def semitones(self, channel=0):
        """The channel's pitch in semitones, and its range."""
        pitch_range = channels.pitch_range.get(channel, 2)
        return round(channels.pitch.get(channel, 0.0) * pitch_range), pitch_range

    def test_semitone_steps_stay_in_the_default_range(self):
        self.shifted_hit("PAD_13")  # semitone up
        self.assertEqual(channels.pitch[0], 0.5)  # +1 of the default +-2
        self.assertEqual(channels.pitch_calls, [(0, 0.5, 0)])  # range untouched
        self.assertEqual(ui.hints, ["Channel pitch: +1 semitones (range +/-2)"])
        self.shifted_hit("PAD_14")
        self.shifted_hit("PAD_14")
        self.assertEqual(self.semitones(), (-1, 2))

    def test_octave_widens_the_range(self):
        self.shifted_hit("PAD_16")  # octave up
        self.assertEqual(channels.pitch_calls, [(0, 12, 2), (0, 1.0, 0)])  # range first, then pitch
        self.assertEqual(self.semitones(), (12, 12))
        self.shifted_hit("PAD_13")
        self.assertEqual(self.semitones(), (13, 24))
        self.assertEqual(ui.hints[-1], "Channel pitch: +13 semitones (range +/-24)")

    def test_range_is_never_narrowed(self):
        self.shifted_hit("PAD_16")
        self.shifted_hit("PAD_15")  # octave down
        self.shifted_hit("PAD_15")
        self.assertEqual(self.semitones(), (-12, 12))
        self.shifted_hit("PAD_16")
        self.assertEqual(self.semitones(), (0, 12))

    def test_pitch_is_clamped_to_the_largest_range(self):
        for _ in range(6):
            self.shifted_hit("PAD_16")
        self.assertEqual(self.semitones(), (pads.MAX_PITCH_RANGE, pads.MAX_PITCH_RANGE))
        for _ in range(10):
            self.shifted_hit("PAD_15")
        self.assertEqual(self.semitones(), (-pads.MAX_PITCH_RANGE, pads.MAX_PITCH_RANGE))

    def test_changes_the_selected_channel(self):
        channels.selected = 2
        channels.pitch_range[2] = 24
        self.shifted_hit("PAD_16")
        self.assertEqual(channels.pitch_calls, [(2, 0.5, 0)])  # +12 fits in +-24

    def test_nothing_without_a_selected_channel(self):
        channels.selected = -1
        self.shifted_hit("PAD_13")
        self.assertEqual(channels.pitch_calls, [])
        self.assertEqual(ui.hints, [])

    def test_pads_play_their_own_notes(self):
        self.shifted_hit("PAD_16")
        self.assertEqual(self.send(note_on(controls.BY_ID["PAD_1"].number)).data1, 48)  # Group D

    def test_works_in_fpc_mode(self):
        plugins.names[1] = "FPC"
        plugins.pads[1] = [(36 + i, 0xFF0000, False) for i in range(32)]
        channels.selected = 1
        self.refresh()
        self.controller.state.mode = SHIFT
        self.refresh()
        for pad_id in ("PAD_14", "PAD_13", "PAD_16", "PAD_15"):
            self.assertEqual(self.controller.leds._sent[pad_id], colors.PURPLE, pad_id)
        self.shifted_hit("PAD_13")
        self.assertEqual(self.semitones(1), (1, 2))


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
        self.refresh()

    def select_channel(self, channel):
        channels.selected = channel
        device.reset()
        self.refresh()

    def pad_leds(self):
        return {pad_id: self.controller.leds._sent[pad_id] for pad_id in PAD_IDS}

    def test_selecting_fpc_jumps_to_group_c_once(self):
        self.select_fpc()
        self.assertEqual(self.controller.state.pad_group, 4)
        self.send(cc(controls.BY_ID["GROUP_F"].number))
        self.refresh()
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

    def test_fixed_velocity_applies_in_fpc_mode(self):
        self.select_fpc()
        self.send(cc(controls.BY_ID["PAD_MODE"].number))
        event = self.send(note_on(controls.BY_ID["PAD_1"].number, 30))
        self.assertEqual((event.data1, event.data2), (36, 127))

    def test_leaving_fpc_restores_chromatic_layout(self):
        self.select_fpc()
        self.select_channel(0)
        self.assertEqual(self.send(note_on(controls.BY_ID["PAD_1"].number)).data1, 64)  # Group E, chromatic
        self.assertEqual(self.pad_leds()["PAD_1"], RED)


if __name__ == "__main__":
    unittest.main()
