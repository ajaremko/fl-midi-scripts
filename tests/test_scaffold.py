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

import device_FLC_MaschineMK2_Hardware as script  # noqa: E402
import device_FLC_MaschineMK2_Bridge as bridge_script  # noqa: E402
from flc_maschine import bindings, bridge_link, controls, diagnostics, feedback, log, macros, notes  # noqa: E402
from flc_maschine.state import COLOR, DEFAULT_PADS, KEYBOARD, NEW, SEQUENCER, SHIFT  # noqa: E402
from flc_maschine import controller as controller_module  # noqa: E402
from flc_maschine.controller import MaschineMk2  # noqa: E402
from flc_maschine.rendering import colors, renderer  # noqa: E402
from flc_maschine.handlers import channel_colors, channel_knobs, macro_knobs, note_repeat, pads, presets, transport_controls, ui_commands  # noqa: E402
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
        plugins.effects = {}
        plugins.params = {}
        plugins.set_calls = []
        mixer.active_effect = None
        channels.types = {}
        log.DEBUG_FPC_COLORS = False
        ui.focused = None
        ui.snap_mode = midi.Snap_None
        ui.in_popup_menu = False
        ui.hints = []
        ui.event_editors = []
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
        general.rec_events = []
        general.rec_values = {}
        channels.fx_tracks = {}
        channels.inc_calls = []
        general.safe = True
        diagnostics.ENABLED = False
        mixer.track_volume = {0: 0.8}
        mixer.track_number = 0
        mixer.track_count = 10
        mixer.selected_tracks = set()
        mixer.tempo = 120.0
        mixer.track_names = {}
        mixer.track_colors = {}
        mixer.track_effects = set()
        mixer.track_number_flags = []
        channels.global_count = None
        channels.names = {}
        plugins.presets = {}
        plugins.preset_index = {}
        plugins.preset_calls = []
        plugins.preset_pending = False
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

    def test_f3_toggles_shift_and_its_led(self):
        f3 = controls.BY_ID["F3"].number

        self.assertTrue(self.send(cc(f3)).handled)
        self.assertEqual(self.controller.state.mode, SHIFT)
        self.assertIn((midi.MIDI_CONTROLCHANGE, f3, 127), [unpack(m) for m in device.sent])

        self.send(cc(f3))
        self.assertIsNone(self.controller.state.mode)
        self.assertIn((midi.MIDI_CONTROLCHANGE, f3, 0), [unpack(m) for m in device.sent])

    def test_pressed_button_led_is_reasserted(self):
        # A toggle button lights itself on the hardware, so the script resends "off".
        erase = controls.BY_ID["ERASE"].number
        self.send(cc(erase))
        self.assertEqual([unpack(m) for m in device.sent], [(midi.MIDI_CONTROLCHANGE, erase, 0)])

    def test_f1_f2_f9_f10_send_menu_escape_and_item_menu(self):
        buttons = (("F1", midi.FPT_Menu), ("F2", midi.FPT_Escape), ("F9", midi.FPT_ItemMenu), ("F10", midi.FPT_Escape))
        for button, command in buttons:
            with self.subTest(button=button):
                del transport.calls[:]
                self.send(cc(controls.BY_ID[button].number))
                self.assertEqual(transport.calls, [("globalTransport", command, 1)])
                self.assertIsNone(self.controller.state.mode)
                self.assertFalse(self.controller.leds._sent[button])

    def test_f1_is_the_plain_menu_in_every_window(self):
        for window in (midi.widBrowser, midi.widPianoRoll, midi.widMixer, midi.widChannelRack, midi.widPlaylist):
            with self.subTest(window=window):
                ui.focused = window
                del transport.calls[:]
                self.send(cc(controls.BY_ID["F1"].number))
                self.assertEqual(transport.calls, [("globalTransport", midi.FPT_Menu, 1)])

    def test_f11_is_a_second_shift_button_and_both_light(self):
        self.send(cc(controls.BY_ID["F11"].number))
        self.assertEqual(self.controller.state.mode, SHIFT)
        self.assertTrue(self.controller.leds._sent["F3"])
        self.assertTrue(self.controller.leds._sent["F11"])
        self.send(cc(controls.BY_ID["F3"].number))  # either button turns it off
        self.assertIsNone(self.controller.state.mode)
        self.assertFalse(self.controller.leds._sent["F3"])
        self.assertFalse(self.controller.leds._sent["F11"])

    def test_pads_pass_through_to_fl_at_group_d_notes(self):
        pad_1 = controls.BY_ID["PAD_1"].number
        event = self.send(note_on(pad_1))
        self.assertFalse(event.handled)
        self.assertEqual(event.data1, 48)
        event = self.send(note_off(pad_1))
        self.assertFalse(event.handled)
        self.assertEqual(event.data1, 48)
        self.assertEqual(self.send(note_on(controls.BY_ID["PAD_13"].number)).data1, 60)  # middle C

    def test_f15_toggles_fixed_velocity_and_its_led(self):
        self.send(cc(controls.BY_ID["F15"].number))
        self.assertTrue(self.controller.state.fixed_velocity)
        self.assertTrue(self.controller.leds._sent["F15"])
        self.assertFalse(self.controller.leds._sent["PAD_MODE"])  # Pad Mode is the pad mode override now
        self.send(cc(controls.BY_ID["F15"].number))
        self.assertFalse(self.controller.state.fixed_velocity)
        self.assertFalse(self.controller.leds._sent["F15"])

    def test_fixed_velocity_plays_pads_at_full_velocity(self):
        pad_1 = controls.BY_ID["PAD_1"].number
        self.assertEqual(self.send(note_on(pad_1, 40)).data2, 40)  # off: real velocity
        self.send(note_off(pad_1))
        self.send(cc(controls.BY_ID["F15"].number))
        event = self.send(note_on(pad_1, 40))
        self.assertFalse(event.handled)
        self.assertEqual((event.data1, event.data2), (48, 127))  # still translated
        event = self.send(note_off(pad_1))
        self.assertEqual((event.data1, event.data2), (48, 0))  # note-off untouched

    def test_fixed_velocity_leaves_aftertouch_alone(self):
        pad_1 = controls.BY_ID["PAD_1"].number
        self.send(cc(controls.BY_ID["F15"].number))
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
        self.send(cc(controls.BY_ID["F3"].number))  # shift on while the pad is held
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
        self.send(cc(controls.BY_ID["F3"].number))  # shift on while the pad is held
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


    def test_unmapped_message_is_swallowed(self):
        self.assertTrue(self.send(cc(0)).handled)  # unmapped: logged, not passed to FL

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
        self.send(cc(controls.BY_ID["F3"].number))
        lit = {control_id for control_id, value in self.controller.leds._sent.items()
               if value not in (False, colors.OFF)}
        self.assertIn("F3", lit)
        self.assertIn("PAD_1", lit)
        device.reset()
        script.OnDeInit()
        sent = [unpack(m) for m in device.sent]
        self.assertTrue(all(value == 0 for _, _, value in sent))
        self.assertEqual({data1 for _, data1, _ in sent}, {controls.BY_ID[c].number for c in lit})


WINDOW_BUTTONS = {
    "BROWSE": midi.widBrowser,
    "F5": midi.widChannelRack,
    "F6": midi.widPianoRoll,
    "F7": midi.widPlaylist,
    "F8": midi.widMixer,
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


BRIDGE_CC = midi.MIDI_CONTROLCHANGE + bridge_link.CHANNEL  # control changes on channel 16


# Everything the script tells the bridge: repeat off, rate 1/16 (6 clocks), 120.0 BPM, stopped,
# pads playing notes.
FULL_STATE = [(1, 0), (2, 0), (34, 6), (3, 9), (35, 48), (4, 0), (5, 127)]


def bridge_ccs():
    """(control, value) of each channel-16 control change the script sent, in order."""
    return [(d1, d2) for status, d1, d2 in map(unpack, device.sent) if status == BRIDGE_CC]


class EntryScriptsTest(unittest.TestCase):
    def test_each_entry_script_names_its_connection(self):
        for filename, name in (("device_FLC_MaschineMK2_Hardware.py", "FL Complete Maschine MK2 (Hardware)"),
                               ("device_FLC_MaschineMK2_Bridge.py", "FL Complete Maschine MK2 (Bridge)")):
            with self.subTest(filename=filename):
                with open(os.path.join(ROOT, filename)) as f:
                    self.assertEqual(f.readline().strip(), "# name=" + name)  # FL reads line 1

    def test_the_entry_scripts_set_the_mode(self):
        self.assertFalse(script.controller.bridge)
        self.assertTrue(bridge_script.controller.bridge)


class HardwareModeTest(ScriptTestCase):
    def test_note_repeat_is_a_placeholder_and_nothing_goes_to_a_bridge(self):
        event = self.send(cc(controls.BY_ID["NOTE_REPEAT"].number))
        self.assertTrue(event.handled)
        self.assertIn("unimplemented: NOTE_REPEAT", self.log.getvalue())
        self.assertFalse(self.controller.state.note_repeat)
        self.assertFalse(self.controller.leds._sent["NOTE_REPEAT"])
        device.reset()
        self.refresh()
        script.OnInit()
        self.assertEqual(bridge_ccs(), [])


class BridgeModeTest(ScriptTestCase):
    """The Bridge entry script: Note Repeat state sent to the MK2 bridge on channel 16."""

    def setUp(self):
        super().setUp()
        bridge_script.controller = MaschineMk2(bridge=True)
        self.controller = bridge_script.controller
        device.reset()
        bridge_script.OnInit()

    def send(self, event):
        device.reset()
        bridge_script.OnMidiMsg(event)
        bridge_script.OnIdle()
        return event

    def refresh(self, flags=0):
        bridge_script.OnRefresh(flags)
        bridge_script.OnIdle()

    def test_init_sends_the_full_state(self):
        # Off; 1/16 is 6 clocks; 120.0 BPM is 1200 = 9 * 128 + 48; stopped.
        self.assertEqual(bridge_ccs(), FULL_STATE)

    def press_note_repeat(self):
        # A toggle button: FL sees 127 and 0 on alternate presses, and each is a press.
        self.presses = getattr(self, "presses", 0) + 1
        return self.send(cc(controls.BY_ID["NOTE_REPEAT"].number, 127 if self.presses % 2 else 0))

    def test_note_repeat_cycles_off_on_triplets(self):
        state = self.controller.state
        self.press_note_repeat()
        self.assertEqual(state.note_repeat, note_repeat.ON)
        self.assertTrue(self.controller.leds._sent["NOTE_REPEAT"])
        self.assertEqual(ui.hints[-1], "Note Repeat: 1/16")
        self.assertEqual(bridge_ccs(), [(1, 127)])  # only what changed
        self.press_note_repeat()
        self.assertEqual(state.note_repeat, note_repeat.TRIPLETS)
        self.assertTrue(self.controller.leds._sent["NOTE_REPEAT"])
        self.assertEqual(ui.hints[-1], "Note Repeat: triplets, 1/16T")
        self.assertEqual(bridge_ccs(), [(2, 0), (34, 4)])  # still on; now 1/16T
        self.press_note_repeat()
        self.assertEqual(state.note_repeat, note_repeat.OFF)
        self.assertFalse(self.controller.leds._sent["NOTE_REPEAT"])
        self.assertEqual(ui.hints[-1], "Note Repeat: off")
        self.assertEqual(bridge_ccs(), [(1, 0), (2, 0), (34, 6)])

    def turn(self, delta):
        del transport.calls[:]
        return self.send(cc(controls.BY_ID["ENCODER"].number, delta & 0x7F))

    def rates_turning(self, delta, times):
        names = []
        for _ in range(times):
            self.turn(delta)
            names.append(note_repeat.rate_name(self.controller.state))
        return names

    def test_encoder_steps_through_the_straight_rates_in_on(self):
        self.press_note_repeat()
        ui.focused = midi.widChannelRack
        self.turn(+1)  # clockwise: faster
        self.assertEqual(ui.hints[-1], "Note Repeat: 1/32")
        self.assertEqual(bridge_ccs(), [(2, 0), (34, 3)])
        self.assertEqual(transport.calls, [])  # no navigation
        self.turn(+1)
        self.assertEqual(bridge_ccs(), [])  # clamped at 1/32: nothing new
        self.assertEqual(self.rates_turning(-1, 4), ["1/16", "1/8", "1/4", "1/4"])

    def test_encoder_steps_through_the_triplet_rates_in_triplets(self):
        self.press_note_repeat()
        self.press_note_repeat()
        self.assertEqual(self.rates_turning(+1, 2), ["1/32T", "1/32T"])
        self.assertEqual(self.rates_turning(-1, 4), ["1/16T", "1/8T", "1/4T", "1/4T"])
        self.assertEqual(ui.hints[-1], "Note Repeat: 1/4T")

    def test_the_division_carries_across_modes(self):
        self.press_note_repeat()
        self.turn(-1)  # 1/8
        self.press_note_repeat()
        self.assertEqual(note_repeat.rate_name(self.controller.state), "1/8T")
        self.assertEqual(bridge_ccs(), [(2, 0), (34, 8)])

    def test_note_repeat_takes_the_encoder_from_overrides_and_selection(self):
        self.send(cc(controls.BY_ID["VOLUME"].number))  # volume override
        self.press_note_repeat()
        ui.focused = midi.widChannelRack
        self.send(cc(controls.BY_ID["ENCODER_PUSH"].number, 127))  # held: would drag-select
        self.turn(+1)
        self.send(cc(controls.BY_ID["ENCODER_PUSH"].number, 0))
        self.assertEqual(mixer.track_volume[0], 0.8)
        self.assertEqual(channels.selection, set())
        self.assertEqual(transport.calls, [])  # and the release doesn't click
        self.assertEqual(note_repeat.rate_name(self.controller.state), "1/32")

    def test_encoder_is_unchanged_with_note_repeat_off(self):
        ui.focused = midi.widChannelRack
        self.turn(+1)
        self.assertEqual(transport.calls, [("globalTransport", midi.FPT_Down, 1)])
        self.assertEqual(note_repeat.rate_name(self.controller.state), "1/16")

    def test_the_snap_no_longer_changes_the_rate(self):
        ui.snap_mode = midi.Snap_Beat
        device.reset()
        self.refresh()
        self.assertEqual(bridge_ccs(), [])

    def test_pad_modes_without_notes_tell_the_bridge(self):
        self.send(cc(controls.BY_ID["PAD_MODE"].number))
        for delta, value in ((1, 127), (1, 0), (-1, 127), (-1, 127)):  # Keyboard, Sequencer, Keyboard, Default
            self.send(cc(controls.BY_ID["ENCODER"].number, delta & 0x7F))
            self.assertEqual(self.controller.state.pad_mode == SEQUENCER, value == 0)
            if bridge_ccs():
                self.assertEqual(bridge_ccs(), [(5, value)])
        self.assertEqual(self.controller.state.pad_mode, DEFAULT_PADS)

    def test_modes_tell_the_bridge_the_pads_are_not_notes(self):
        for button in ("F3", "F4", "F12"):
            with self.subTest(button=button):
                self.send(cc(controls.BY_ID[button].number))
                self.assertEqual(bridge_ccs(), [(5, 0)])
                self.send(cc(controls.BY_ID[button].number, 0))
                self.assertEqual(bridge_ccs(), [(5, 127)])

    def test_play_state_is_sent(self):
        transport.playing = True
        device.reset()
        self.refresh()
        self.assertEqual(bridge_ccs(), [(4, 127)])
        transport.playing = False
        device.reset()
        self.refresh()
        self.assertEqual(bridge_ccs(), [(4, 0)])

    def test_no_clock_warning_is_shown_once(self):
        warning = FakeEvent(midi.MIDI_CONTROLCHANGE, bridge_link.CC_NO_CLOCK, 127, channel=bridge_link.CHANNEL)
        for _ in range(3):
            self.assertTrue(self.send(warning).handled)
        self.assertEqual(ui.hints.count(bridge_link.NO_CLOCK_WARNING), 1)
        self.assertEqual(self.log.getvalue().count("Send master sync"), 1)
        self.assertFalse(self.controller.guard.tripped)

    def test_tempo_is_sent_in_tenths_and_normalised(self):
        mixer.tempo = 128.5
        device.reset()
        self.refresh()
        self.assertEqual(bridge_ccs(), [(3, 10), (35, 5)])  # 1285 = 10 * 128 + 5
        mixer.tempo = 140000.0  # BPM x 1000, as some FL versions report it
        device.reset()
        self.refresh()
        self.assertEqual(bridge_ccs(), [(3, 10), (35, 120)])  # 1400

    def test_unchanged_state_is_not_resent(self):
        device.reset()
        self.refresh()
        self.assertEqual(bridge_ccs(), [])

    def test_bridge_hello_resends_everything(self):
        hello = FakeEvent(midi.MIDI_CONTROLCHANGE, bridge_link.CC_HELLO, 127, channel=bridge_link.CHANNEL)
        self.send(hello)
        self.assertTrue(hello.handled)
        self.assertNotIn("unmapped", self.log.getvalue())
        self.assertEqual(bridge_ccs(), FULL_STATE)
        leds = [m for m in device.sent if unpack(m)[0] != BRIDGE_CC]
        self.assertIn((midi.MIDI_CONTROLCHANGE, controls.BY_ID["SCENE"].number, 0), map(unpack, leds))
        self.assertTrue(any(unpack(m)[1] == controls.BY_ID["PAD_1"].number for m in leds))

    def test_rechecks_tempo_while_note_repeat_is_on(self):
        self.send(cc(controls.BY_ID["NOTE_REPEAT"].number))
        mixer.tempo = 90.0  # changed without a refresh
        device.reset()
        for _ in range(controller_module.BRIDGE_RECHECK_IDLES):
            bridge_script.OnIdle()
        self.assertEqual(bridge_ccs(), [(3, 7), (35, 4)])  # 900 = 7 * 128 + 4

    def test_deinit_turns_note_repeat_off_in_the_bridge(self):
        self.send(cc(controls.BY_ID["NOTE_REPEAT"].number))
        device.reset()
        bridge_script.OnDeInit()
        self.assertEqual(bridge_ccs(), [(1, 0)])


class FeedbackGuardTest(ScriptTestCase):
    """The script's own output routed back into its input (see feedback.py)."""

    def echo(self, messages, entry=script):
        """Feed sent messages back in as input, as a feedback loop would, then run OnIdle."""
        for message in messages:
            status, data1, data2 = unpack(message)
            entry.OnMidiMsg(FakeEvent(status & 0xF0, data1, data2, channel=status & 0x0F))
        entry.OnIdle()

    def run_loop(self, rounds, entry=script):
        """Echo everything the script sends, round after round."""
        for _ in range(rounds):
            sent = list(device.sent)
            device.reset()
            self.echo(sent, entry)

    def test_an_echoed_colour_message_trips_the_guard(self):
        event = FakeEvent(midi.MIDI_NOTEON, controls.BY_ID["PAD_1"].number, 127, channel=1)
        script.OnMidiMsg(event)
        self.assertTrue(event.handled)
        self.assertTrue(self.controller.guard.tripped)
        self.assertEqual(self.log.getvalue().count("receiving its own output"), 1)
        self.assertIn(feedback.WARNING, ui.hints)

    def test_once_tripped_input_is_ignored_and_nothing_is_sent(self):
        script.OnMidiMsg(FakeEvent(midi.MIDI_CONTROLCHANGE, 80, 5, channel=2))
        del transport.calls[:]
        event = self.send(cc(controls.BY_ID["SCENE"].number))
        self.assertTrue(event.handled)
        self.assertEqual(transport.calls, [])
        self.refresh()
        script.OnDeInit()
        self.assertEqual(device.sent, [])
        self.assertEqual(self.log.getvalue().count("receiving its own output"), 1)  # warned once

    def test_a_pad_loop_is_stopped_at_once(self):
        self.send(note_on(controls.BY_ID["PAD_1"].number))  # the pad's LED is resent
        self.run_loop(3)
        self.assertTrue(self.controller.guard.tripped)
        self.assertEqual(device.sent, [])

    def test_a_scene_loop_on_channel_1_is_stopped(self):
        self.send(cc(controls.BY_ID["SCENE"].number))  # toggles song mode, so the Scene LED changes
        self.run_loop(30)
        self.assertTrue(self.controller.guard.tripped)
        toggles = transport.calls.count(("setLoopMode",))
        self.assertLessEqual(toggles, feedback.ECHO_LIMIT + 1)  # stopped, not runaway
        self.assertEqual(device.sent, [])

    def test_ordinary_presses_do_not_trip_it(self):
        for _ in range(3):
            self.send(cc(controls.BY_ID["SCENE"].number))
            self.send(cc(controls.BY_ID["PAD_MODE"].number))
        for _ in range(20):
            self.send(note_on(controls.BY_ID["PAD_1"].number))
            self.send(note_off(controls.BY_ID["PAD_1"].number))
        self.assertFalse(self.controller.guard.tripped)

    def test_bridge_mode_trips_on_its_own_channel_16_messages_but_not_the_hello(self):
        bridge_script.controller = MaschineMk2(bridge=True)
        bridge_script.OnInit()
        hello = FakeEvent(midi.MIDI_CONTROLCHANGE, bridge_link.CC_HELLO, 127, channel=bridge_link.CHANNEL)
        bridge_script.OnMidiMsg(hello)
        self.assertFalse(bridge_script.controller.guard.tripped)
        bridge_script.OnMidiMsg(FakeEvent(midi.MIDI_CONTROLCHANGE, bridge_link.CC_REPEAT, 0,
                                          channel=bridge_link.CHANNEL))
        self.assertTrue(bridge_script.controller.guard.tripped)

    def test_fls_all_notes_off_burst_is_not_an_echo(self):
        # After a MIDI input overflow (or a panic) FL sends All Notes Off on all 16 channels.
        del transport.calls[:]
        for channel in range(16):
            event = FakeEvent(midi.MIDI_CONTROLCHANGE, 123, 0, channel=channel)
            script.OnMidiMsg(event)
            self.assertTrue(event.handled)
        script.OnIdle()
        self.assertFalse(self.controller.guard.tripped)
        self.assertNotIn("unmapped", self.log.getvalue())
        self.assertEqual(transport.calls, [])

    def test_the_trip_warning_names_the_message(self):
        script.OnMidiMsg(FakeEvent(midi.MIDI_CONTROLCHANGE, 80, 5, channel=1))
        self.assertIn("(tripped by channel 2 CC 80 = 5)", self.log.getvalue())

    def test_hardware_mode_ignores_channel_16(self):
        script.OnMidiMsg(FakeEvent(midi.MIDI_CONTROLCHANGE, 1, 0, channel=15))
        self.assertFalse(self.controller.guard.tripped)

    def test_reloading_the_script_starts_clean(self):
        script.OnMidiMsg(FakeEvent(midi.MIDI_NOTEON, 12, 1, channel=2))
        script.controller = MaschineMk2()
        device.reset()
        script.OnInit()
        self.assertFalse(script.controller.guard.tripped)
        self.assertTrue(device.sent)  # LEDs sent again


class ChannelKnobsTest(ScriptTestCase):
    """E1-E8: the selected channel's settings, as channel REC events."""

    SET = midi.REC_UpdateValue | midi.REC_UpdateControl | midi.REC_ShowHint

    def turn(self, knob, delta):
        return self.send(cc(controls.BY_ID[knob].number, delta & 0x7F))  # relative, two's complement

    def test_each_knob_steps_its_parameter_on_the_selected_channel(self):
        channels.selected = 2
        base = channels.getRecEventId(2)
        for knob, offset in (("E1", midi.REC_Chan_Vol), ("E2", midi.REC_Chan_Pan), ("E3", midi.REC_Chan_Pitch),
                             ("E5", midi.REC_Chan_GateTime),
                             ("E6", midi.REC_Chan_TimeOfs), ("E7", midi.REC_Chan_SwingMix)):
            with self.subTest(knob=knob):
                general.rec_events = []
                self.assertTrue(self.turn(knob, +3).handled)
                self.turn(knob, -1)
                self.assertEqual(general.rec_events, [(base + offset, 3, self.SET), (base + offset, 2, self.SET)])
                self.assertEqual(channels.inc_calls[-1], (base + offset, -1, midi.EKRes))

    def test_range_knob_sets_the_pitch_range_a_semitone_per_step(self):
        channels.selected = 3
        self.turn("E4", +5)  # one semitone per message, however fast
        self.assertEqual(channels.pitch_range[3], 3)  # from FL's default 2
        self.assertEqual(ui.hints[-1], "Pitch range: +/-3 semitones")
        for _ in range(60):
            self.turn("E4", +1)
        self.assertEqual(channels.pitch_range[3], pads.MAX_PITCH_RANGE)
        for _ in range(60):
            self.turn("E4", -1)
        self.assertEqual(channels.pitch_range[3], 1)
        self.assertEqual(general.rec_events, [])  # not a REC event

    def test_mixer_knob_routes_one_track_per_step_within_range(self):
        channels.selected = 1
        event_id = channels.getRecEventId(1) + midi.REC_Chan_FXTrack
        self.turn("E8", +5)  # one track per message, however fast
        self.assertEqual(general.rec_events[-1], (event_id, 1, midi.REC_Control | midi.REC_UpdateControl))
        self.assertEqual(ui.hints[-1], "Mixer track: 1 Insert 1")
        for _ in range(20):
            self.turn("E8", +1)
        self.assertEqual(channels.getTargetFxTrack(1), mixer.track_count - 2)  # stops before "Current"
        for _ in range(20):
            self.turn("E8", -1)
        self.assertEqual(channels.getTargetFxTrack(1), 0)
        self.assertEqual(ui.hints[-1], "Mixer track: 0 Master")

    def test_nothing_without_a_selected_channel(self):
        channels.selected = -1
        self.turn("E1", +1)
        self.turn("E8", +1)
        self.assertEqual(general.rec_events, [])
        self.assertEqual(ui.hints[-1], "No channel selected")

    def test_the_knobs_work_the_same_in_shift_mode(self):
        self.controller.state.mode = SHIFT
        self.turn("E1", +1)
        self.assertEqual(len(general.rec_events), 1)

    def test_page_two_knobs_are_macros_not_channel_settings(self):
        self.assertTrue(self.turn("E9", +1).handled)
        self.assertEqual(general.rec_events, [])


class MacroMappingsTest(unittest.TestCase):
    def test_mappings_are_well_formed(self):
        for name, mapping in list(macros.MACROS.items()) + list(macros.CHANNEL_MACROS.items()):
            with self.subTest(plugin=name):
                self.assertLessEqual(len(mapping), 8)
        for name, mapping in macros.MACROS.items():
            with self.subTest(plugin=name):
                entries = [entry.strip().lower() if isinstance(entry, str) else entry
                           for entry in mapping if entry is not None]
                self.assertTrue(all(isinstance(entry, (str, int)) for entry in entries))
                self.assertEqual(len(entries), len(set(entries)), "a parameter mapped twice")


class MacroKnobsTest(ScriptTestCase):
    """E9-E16: macros for the focused plugin, from mappings in macros.py (replaced here by test ones)."""

    def setUp(self):
        super().setUp()
        self._macros, self._channel_macros = dict(macros.MACROS), dict(macros.CHANNEL_MACROS)
        macros.MACROS.clear()
        macros.MACROS.update({
            "Synth": [" CUTOFF ", "Resonance", None, "Wave", "Missing"],
            "Reverb": ["Size"],
            "Flexible": [2, 7],
            "Empty": [],
        })
        macros.CHANNEL_MACROS.clear()
        macros.CHANNEL_MACROS.update({"Sampler": [midi.REC_Chan_Pitch]})
        channels.selected = 1
        plugins.names[1] = "Synth"
        plugins.params[(1, -1)] = [["Cutoff", 0.5, None], ["Resonance", 0.25, None], ["Wave", 0.0, 4]]

    def tearDown(self):
        macros.MACROS.clear()
        macros.MACROS.update(self._macros)
        macros.CHANNEL_MACROS.clear()
        macros.CHANNEL_MACROS.update(self._channel_macros)
        super().tearDown()

    def turn(self, knob, delta):
        return self.send(cc(controls.BY_ID[knob].number, delta & 0x7F))

    def value(self, index, slot, param):
        return plugins.params[(index, slot)][param][1]

    def test_knobs_step_their_named_parameters(self):
        self.assertTrue(self.turn("E9", +2).handled)
        self.assertAlmostEqual(self.value(1, -1, 0), 0.5 + 2 * macro_knobs.MACRO_STEP)  # " CUTOFF " matched
        self.assertEqual(ui.hints[-1], "Cutoff: 52%")
        self.turn("E10", -1)
        self.assertAlmostEqual(self.value(1, -1, 1), 0.25 - macro_knobs.MACRO_STEP)
        self.assertTrue(all(call[4] == midi.PIM_None for call in plugins.set_calls))

    def test_the_first_write_rewrites_the_current_value(self):
        self.turn("E9", +1)
        self.assertEqual(plugins.set_calls[0], (0.5, 0, 1, -1, midi.PIM_None))
        count = len(plugins.set_calls)
        self.turn("E9", +1)
        self.assertEqual(len(plugins.set_calls), count + 1)  # only once

    def test_a_focused_mixer_effect_comes_first(self):
        plugins.effects[(3, 2)] = "Reverb"
        plugins.params[(3, 2)] = [["Size", 0.5, None]]
        mixer.active_effect = (3, 2)
        self.turn("E9", +1)
        self.assertGreater(self.value(3, 2, 0), 0.5)
        self.assertEqual(self.value(1, -1, 0), 0.5)  # the channel's plugin untouched

    def test_a_stepped_parameter_moves_once_the_steps_add_up(self):
        # Wave has 4 steps (0, 0.25, ...): at 1/128 per knob step it rounds up to 0.25 at the 17th.
        for _ in range(15):
            self.turn("E12", +1)
        self.assertEqual(self.value(1, -1, 2), 0.0)
        for _ in range(2):
            self.turn("E12", +1)
        self.assertEqual(self.value(1, -1, 2), 0.25)

    def test_a_value_changed_elsewhere_restarts_the_knob(self):
        self.turn("E9", +1)
        plugins.params[(1, -1)][0][1] = 0.9  # moved with the mouse
        self.turn("E9", +1)
        self.assertAlmostEqual(self.value(1, -1, 0), 0.9 + macro_knobs.MACRO_STEP)

    def test_values_are_clamped(self):
        plugins.params[(1, -1)][0][1] = 0.995
        self.turn("E9", +5)
        self.assertEqual(self.value(1, -1, 0), 1.0)

    def test_parameters_can_be_mapped_by_number(self):
        plugins.names[1] = "Flexible"
        plugins.params[(1, -1)] = [["Not Used", 0.1, None], ["Not Used", 0.2, None], ["Macro", 0.5, None]]
        self.turn("E9", +1)
        self.assertGreater(self.value(1, -1, 2), 0.5)
        self.assertEqual(ui.hints[-1], "Macro: 51%")  # FL's name for the parameter
        self.turn("E10", +1)  # parameter 7 doesn't exist
        self.assertEqual(ui.hints[-1], "Macro 2: no parameter 7 on Flexible")

    def test_unused_and_missing_knobs(self):
        self.turn("E11", +1)
        self.assertEqual(ui.hints[-1], "Macro 3: not used on Synth")
        self.turn("E13", +1)
        self.assertEqual(ui.hints[-1], "Macro 5: no parameter 'Missing' on Synth")
        self.turn("E13", +1)
        self.assertEqual(self.log.getvalue().count("no parameter 'Missing'"), 1)  # logged once
        self.turn("E16", +1)  # beyond the mapping
        self.assertEqual(ui.hints[-1], "Macro 8: not used on Synth")

    def test_an_unmapped_plugin_logs_its_parameters_once(self):
        plugins.names[1] = "Unknown VST"
        plugins.params[(1, -1)] = [["Gain", 0.5, None], ["", 0.0, None], ["Drive", 0.1, None]]
        self.turn("E9", +1)
        self.assertEqual(ui.hints[-1], "No macros for Unknown VST")
        output = self.log.getvalue()
        self.assertIn("0: Gain", output)
        self.assertIn("2: Drive", output)
        self.assertNotIn(" 1: ", output)  # empty names skipped
        self.turn("E10", +1)
        self.assertEqual(self.log.getvalue().count("No macros for Unknown VST yet"), 1)
        self.assertEqual(plugins.set_calls, [])

    def test_an_empty_mapping_counts_as_unmapped(self):
        plugins.names[1] = "Empty"
        self.turn("E9", +1)
        self.assertEqual(ui.hints[-1], "No macros for Empty")

    def test_sampler_channels_use_channel_macros(self):
        del plugins.names[1]
        channels.types[1] = midi.CT_Sampler
        self.turn("E9", +2)
        event_id = channels.getRecEventId(1) + midi.REC_Chan_Pitch
        self.assertEqual(general.rec_events, [(event_id, 2, channel_knobs.SET_FLAGS)])
        self.turn("E10", +1)
        self.assertEqual(ui.hints[-1], "Macro 2: not used on Sampler")
        macros.CHANNEL_MACROS["Sampler"] = []
        self.turn("E9", +1)
        self.assertEqual(ui.hints[-1], "No macros for Sampler")

    def test_no_plugin_to_act_on(self):
        channels.selected = -1
        self.turn("E9", +1)
        self.assertEqual(ui.hints[-1], "No plugin for macros")

    def test_the_same_in_shift_mode(self):
        self.controller.state.mode = SHIFT
        self.turn("E9", +1)
        self.assertGreater(self.value(1, -1, 0), 0.5)


class ColorModeTest(ScriptTestCase):
    """F12: Color mode, where the pads colour the selected channel(s)."""

    def press(self, control_id, value=127):
        return self.send(cc(controls.BY_ID[control_id].number, value))

    def led(self, control_id):
        return self.controller.leds._sent[control_id]

    def palette_hsb(self, i, brightness):
        return colors.with_brightness(colors.rgb_to_hsb(channel_colors.PALETTE[i]), brightness)

    def test_f12_toggles_color_mode_and_its_led(self):
        self.press("F12")
        self.assertEqual(self.controller.state.mode, COLOR)
        self.assertTrue(self.led("F12"))
        self.press("F12", 0)
        self.assertIsNone(self.controller.state.mode)
        self.assertFalse(self.led("F12"))
        self.assertNotIn("unimplemented: F12", self.log.getvalue())

    def test_color_shift_and_new_replace_each_other(self):
        self.press("F12")
        self.press("F3")
        self.assertEqual(self.controller.state.mode, SHIFT)
        self.assertFalse(self.led("F12"))
        self.press("F12", 0)
        self.assertEqual(self.controller.state.mode, COLOR)
        self.press("F4")
        self.assertEqual(self.controller.state.mode, NEW)

    def test_entering_color_mode_clears_an_encoder_override(self):
        self.press("VOLUME")
        self.press("F12")
        self.assertIsNone(self.controller.state.encoder_mode)

    def test_pads_show_the_palette_with_the_current_colour_brightest(self):
        channels.colors[0] = channel_colors.PALETTE[4]
        self.press("F12")
        for i, pad_id in enumerate(PAD_IDS):
            brightness = renderer.LIT_BRIGHTNESS if i == 4 else renderer.PALETTE_DIM
            self.assertEqual(self.led(pad_id), self.palette_hsb(i, brightness), pad_id)
        for group_id in GROUP_IDS:
            self.assertEqual(self.led(group_id), colors.OFF)

    def test_a_pad_colours_every_selected_channel(self):
        channels.selection = {1, 3}
        self.press("F12")
        event = self.send(note_on(controls.BY_ID["PAD_9"].number))
        self.assertTrue(event.handled)
        self.assertEqual(channels.colors.get(1), channel_colors.PALETTE[8])
        self.assertEqual(channels.colors.get(3), channel_colors.PALETTE[8])
        self.assertNotEqual(channels.colors.get(0), channel_colors.PALETTE[8])
        self.assertEqual(ui.hints[-1], "Channel colour: 9")
        self.assertEqual(self.controller.state.mode, COLOR)  # stays on

    def test_no_channel_selected(self):
        channels.selection = set()
        self.press("F12")
        self.send(note_on(controls.BY_ID["PAD_1"].number))
        self.assertEqual(ui.hints[-1], "No channel selected")

    def test_pads_play_no_notes_in_color_mode(self):
        channels.selection = {0}
        self.press("F12")
        event = self.send(note_on(controls.BY_ID["PAD_1"].number))
        self.assertEqual(event.data1, controls.BY_ID["PAD_1"].number)  # not translated to a note
        self.assertTrue(event.handled)

    def test_an_fpc_channel_shows_the_palette_too(self):
        plugins.names[1] = "FPC"
        plugins.pads[1] = [(36 + i, 0x0000FF, False) for i in range(32)]
        channels.selected = 1
        self.refresh()
        self.press("F12")
        self.assertEqual(self.led("PAD_1"), self.palette_hsb(0, renderer.PALETTE_DIM))


class WindowButtonsTest(ScriptTestCase):
    def lit_window_buttons(self):
        return [button for button in WINDOW_BUTTONS if self.controller.leds._sent[button]]

    def test_press_focuses_and_press_again_hides(self):
        f5 = controls.BY_ID["F5"].number
        self.send(cc(f5))
        self.assertEqual(ui.focused, midi.widChannelRack)
        self.assertEqual([unpack(m) for m in device.sent], [(midi.MIDI_CONTROLCHANGE, f5, 127)])
        self.send(cc(f5))
        self.assertIsNone(ui.focused)
        self.assertEqual([unpack(m) for m in device.sent], [(midi.MIDI_CONTROLCHANGE, f5, 0)])

    def test_each_button_focuses_its_window_and_lights_alone(self):
        for button, window in WINDOW_BUTTONS.items():
            with self.subTest(button=button):
                self.send(cc(controls.BY_ID[button].number))
                self.assertEqual(ui.focused, window)
                self.assertEqual(self.lit_window_buttons(), [button])

    def test_focus_changed_elsewhere_moves_the_light(self):
        self.send(cc(controls.BY_ID["F5"].number))
        ui.focused = midi.widMixer  # e.g. clicked with the mouse
        self.refresh()
        self.assertEqual(self.lit_window_buttons(), ["F8"])

    def test_f5_to_f8_work_the_same_with_shift_on(self):
        # BROWSE has a shift function (plugin picker); F5-F8 don't, so they fall back to base.
        self.controller.state.mode = SHIFT
        self.send(cc(controls.BY_ID["F5"].number))
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
        for mode_button in ("F3", "F4"):
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
        self.send(cc(controls.BY_ID["F3"].number))

    def led(self, control_id):
        return self.controller.leds._sent[control_id]

    def test_shift_lights_only_controls_with_a_shift_function(self):
        ui.focused = midi.widChannelRack
        self.send(cc(controls.BY_ID["VOLUME"].number))  # override on
        self.assertTrue(self.led("F5"))
        self.assertTrue(self.led("VOLUME"))
        self.shift()
        for control_id in ("F3", "BROWSE", "PLAY", "REC", "ALL", "NOTE_REPEAT", "RESTART", "SELECT"):
            self.assertTrue(self.led(control_id), control_id)
        # Controls without a shift function (or with only a placeholder) aren't highlighted.
        for control_id in ("F5", "MUTE", "VOLUME", "F1", "ERASE"):
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
        self.assertTrue(self.led("F5"))
        self.assertFalse(self.led("VOLUME"))  # entering shift turned the override off
        self.assertFalse(self.led("F3"))
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

    def test_shift_all_note_repeat_and_restart_send_their_commands(self):
        for button, command in (("ALL", midi.FPT_Save), ("NOTE_REPEAT", midi.FPT_TapTempo),
                                ("RESTART", midi.FPT_LoopRecord)):
            with self.subTest(button=button):
                self.controller.state.mode = SHIFT
                del transport.calls[:]
                self.send(cc(controls.BY_ID[button].number))
                self.assertEqual(transport.calls, [("globalTransport", command, 1)])
                self.assertEqual(self.controller.state.mode, SHIFT)  # shift stays on

    def test_shift_note_repeat_taps_tempo_in_bridge_mode_too(self):
        bridge_script.controller = MaschineMk2(bridge=True)
        bridge_script.OnInit()
        bridge_script.controller.state.mode = SHIFT
        del transport.calls[:]
        bridge_script.OnMidiMsg(cc(controls.BY_ID["NOTE_REPEAT"].number))
        self.assertEqual(transport.calls, [("globalTransport", midi.FPT_TapTempo, 1)])
        self.assertFalse(bridge_script.controller.state.note_repeat)  # not toggled

    def test_shift_select_opens_the_selected_channels_piano_roll(self):
        channels.selected = 2
        self.shift()
        self.send(cc(controls.BY_ID["SELECT"].number))
        self.assertEqual(ui.event_editors, [(channels.getRecEventId(2) + midi.REC_Chan_PianoRoll, midi.EE_PR)])
        channels.selected = -1
        self.send(cc(controls.BY_ID["SELECT"].number, 0))
        self.assertEqual(len(ui.event_editors), 1)  # no channel selected: nothing

    def test_shift_controls_are_the_shift_layer(self):
        # Only real functions count: unimplemented(...) placeholders are left out.
        self.assertTrue({"PLAY", "REC", "PAD_1", "PAD_11", "ALL"} <= bindings.MODE_CONTROLS[SHIFT])
        self.assertFalse({"PAD_4", "PAD_6"} & bindings.MODE_CONTROLS[SHIFT])
        self.assertTrue(bindings.MODE_CONTROLS[SHIFT] <= frozenset(bindings.LAYERS[SHIFT]))


class MixerTrackTest(ScriptTestCase):
    """F16: route the selected channel(s) to empty mixer tracks, named and coloured after them."""

    def press(self):
        return self.send(cc(controls.BY_ID["F16"].number))

    def route(self, channel):
        return channels.getTargetFxTrack(channel)

    def test_routes_to_the_first_empty_track_and_copies_name_and_colour(self):
        channels.selection = {2}
        channels.names = {2: "Kick"}
        channels.colors = {2: 0x123456}
        channels.fx_tracks = {0: 1, 1: 2}  # tracks 1 and 2 have channels
        self.assertTrue(self.press().handled)
        self.assertEqual(self.route(2), 3)
        self.assertEqual(mixer.getTrackName(3), "Kick")
        self.assertEqual(mixer.track_colors, {3: 0x123456})
        self.assertEqual(mixer.track_number_flags, [(3, midi.curfxScrollToMakeVisible)])
        self.assertEqual(ui.hints[-1], "Mixer track 3: Kick")

    def test_skips_tracks_with_effects_or_a_name(self):
        channels.selection = {0}
        mixer.track_effects = {(1, 9)}  # an effect in the last slot
        mixer.track_names = {2: "Reverb bus"}
        self.press()
        self.assertEqual(self.route(0), 3)

    def test_each_selected_channel_gets_its_own_track(self):
        channels.selection = {1, 3, 4}
        channels.fx_tracks = {0: 2}
        self.press()
        self.assertEqual([self.route(c) for c in (1, 3, 4)], [1, 3, 4])
        self.assertEqual([mixer.getTrackName(t) for t in (1, 3, 4)], ["Channel 2", "Channel 4", "Channel 5"])
        self.assertEqual(ui.hints[-1], "Mixer tracks 1, 3, 4")

    def test_a_channel_on_its_own_track_moves_on(self):
        # As FL does. Its old track keeps the channel's name, so a second press moves on again.
        channels.selection = {0}
        self.press()
        self.assertEqual(self.route(0), 1)
        self.press()
        self.assertEqual(self.route(0), 2)

    def test_channels_in_other_groups_keep_their_tracks(self):
        channels.selection = {0}
        channels.global_count = 10
        channels.fx_tracks = {9: 1}  # a channel outside the current group
        self.press()
        self.assertEqual(self.route(0), 2)

    def test_never_uses_the_current_track(self):
        # Inserts 1-8 all taken: track 9 is the "Current" utility track (trackCount() - 1).
        channels.selection = {0}
        channels.fx_tracks = {c: c + 1 for c in range(1, 8)}
        channels.global_count = 9
        channels.fx_tracks[8] = 1
        self.press()
        self.assertEqual(self.route(0), 0)
        self.assertEqual(ui.hints[-1], "No empty mixer track")
        self.assertEqual(mixer.track_names, {})

    def test_assigns_what_it_can_when_tracks_run_out(self):
        channels.selection = {0, 1}
        channels.fx_tracks = {c: c - 1 for c in range(2, 8)}  # tracks 1-6 taken; 7 and 8 empty
        mixer.track_names = {8: "Drums"}
        self.press()
        self.assertEqual((self.route(0), self.route(1)), (7, 0))
        self.assertEqual(ui.hints[-1], "No empty mixer track for 1 of 2 channels")

    def test_no_selection(self):
        self.press()
        self.assertEqual(ui.hints, ["No channel selected"])
        self.assertEqual(general.rec_events, [])


class PresetTest(ScriptTestCase):
    """F13/F14: previous and next preset of the selected channel's plugin."""

    def press(self, button):
        self.send(cc(controls.BY_ID[button].number))

    def setUp(self):
        super().setUp()
        channels.selected = 1
        plugins.names = {1: "FLEX"}
        plugins.presets = {1: ["Init", "Bass", "Pad"]}

    def test_f14_and_f13_step_the_selected_channels_presets(self):
        self.press("F14")
        self.press("F13")
        self.press("F13")
        self.assertEqual(plugins.preset_calls, [("next", 1), ("prev", 1), ("prev", 1)])
        self.assertEqual(plugins.preset_index[1], 2)

    def test_name_hint_waits_for_fl_to_report_the_new_preset(self):
        self.press("F14")  # send() runs one OnIdle, while the name still reads ""
        self.assertEqual(ui.hints, [])
        script.OnIdle()
        self.assertEqual(ui.hints, [])
        plugins.settle()
        script.OnIdle()
        self.assertEqual(ui.hints, ["Preset: Bass"])
        script.OnIdle()
        self.assertEqual(ui.hints, ["Preset: Bass"])  # shown once

    def test_name_hint_appears_anyway_after_the_wait(self):
        plugins.presets = {1: ["Only"]}  # stepping keeps the same name
        self.press("F14")
        plugins.settle()
        for _ in range(presets.PRESET_WAIT_TICKS):
            script.OnIdle()
        self.assertEqual(ui.hints, ["Preset: Only"])

    def test_hints_when_there_is_nothing_to_step(self):
        cases = [
            (-1, {}, {}, "No channel selected"),
            (2, {}, {}, "No plugin on this channel"),  # e.g. a Sampler
            (2, {2: "Fruity Kick"}, {}, "No presets"),
        ]
        for selected, names, preset_lists, hint in cases:
            with self.subTest(hint=hint):
                channels.selected, plugins.names, plugins.presets = selected, names, preset_lists
                ui.hints = []
                self.press("F14")
                self.assertEqual(ui.hints, [hint])
        self.assertEqual(plugins.preset_calls, [])

    def test_buttons_stay_dark(self):
        for button in ("F13", "F14", "F16"):
            with self.subTest(button=button):
                self.press(button)
                self.assertFalse(self.controller.leds._sent[button])
                self.assertNotIn("unimplemented: " + button, self.log.getvalue())


class PadModeTest(ScriptTestCase):
    """Pad Mode: an encoder override that picks the pad mode (Default, Keyboard, Sequencer)."""

    def press(self, control_id, value=127):
        return self.send(cc(controls.BY_ID[control_id].number, value))

    def turn(self, delta):
        del transport.calls[:]
        return self.send(cc(controls.BY_ID["ENCODER"].number, delta & 0x7F))

    def led(self, control_id):
        return self.controller.leds._sent[control_id]

    def pick(self, pad_mode):
        self.press("PAD_MODE")
        for _ in range(PAD_MODES_ORDER.index(pad_mode)):
            self.turn(1)
        self.press("PAD_MODE", 0)  # override off; the pad mode stays

    def test_toggles_the_override_and_its_led(self):
        self.press("PAD_MODE")
        self.assertEqual(self.controller.state.encoder_mode, "PAD_MODE")
        self.assertTrue(self.led("PAD_MODE"))
        self.assertFalse(self.controller.state.fixed_velocity)
        self.assertEqual(ui.hints, ["Pad mode: Default"])
        self.press("PAD_MODE", 0)
        self.assertIsNone(self.controller.state.encoder_mode)
        self.assertFalse(self.led("PAD_MODE"))

    def test_turning_steps_through_the_modes_and_stops_at_the_ends(self):
        self.press("PAD_MODE")
        self.turn(-1)  # already at Default
        self.assertEqual(self.controller.state.pad_mode, DEFAULT_PADS)
        modes = []
        for _ in range(3):
            self.turn(1)
            modes.append(self.controller.state.pad_mode)
        self.assertEqual(modes, [KEYBOARD, SEQUENCER, SEQUENCER])
        self.assertEqual(ui.hints[-3:], ["Pad mode: Keyboard", "Pad mode: Sequencer (not written yet)",
                                         "Pad mode: Sequencer (not written yet)"])
        self.turn(-5)  # one mode per message, however fast
        self.assertEqual(self.controller.state.pad_mode, KEYBOARD)
        self.assertEqual(transport.calls, [])  # no navigation while the override is on

    def test_the_pad_mode_stays_after_the_override_and_the_encoder_navigates_again(self):
        ui.focused = midi.widChannelRack
        self.pick(SEQUENCER)
        self.assertEqual(self.controller.state.pad_mode, SEQUENCER)
        self.turn(1)
        self.assertEqual(transport.calls, [("globalTransport", midi.FPT_Down, 1)])

    def check_silent_dark_pads_and_working_groups(self, pad_mode):
        self.pick(pad_mode)
        event = self.send(note_on(controls.BY_ID["PAD_1"].number))
        self.assertTrue(event.handled)  # not played
        self.assertIn("unimplemented: PAD_1", self.log.getvalue())
        self.send(note_off(controls.BY_ID["PAD_1"].number))
        self.assertTrue(all(self.led("PAD_%d" % (i + 1)) == colors.OFF for i in range(16)))
        self.press("GROUP_B")
        self.assertEqual(self.controller.state.pad_group, 1)
        self.assertNotEqual(self.led("GROUP_B"), colors.OFF)

    def test_sequencer_pads_are_silent_and_dark_until_written(self):
        self.check_silent_dark_pads_and_working_groups(SEQUENCER)

    def test_shift_pads_work_in_every_pad_mode(self):
        self.pick(KEYBOARD)
        self.press("F3")
        self.send(note_on(controls.BY_ID["PAD_1"].number))  # undo
        self.assertIn("undoUp", general.calls)

    def test_default_plays_notes_again(self):
        self.pick(SEQUENCER)
        self.press("PAD_MODE")
        self.turn(-2)
        self.turn(-2)
        event = self.send(note_on(controls.BY_ID["PAD_1"].number))
        self.assertFalse(event.handled)
        self.assertEqual(event.data1, 48)
        self.assertNotEqual(self.led("PAD_2"), colors.OFF)

    def test_entering_shift_turns_the_override_off(self):
        self.press("PAD_MODE")
        self.press("F3")
        self.assertIsNone(self.controller.state.encoder_mode)


PAD_MODES_ORDER = (DEFAULT_PADS, KEYBOARD, SEQUENCER)


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

    def test_f4_toggles_new_mode_and_its_led(self):
        self.press("F4")
        self.assertEqual(self.controller.state.mode, NEW)
        self.assertTrue(self.led("F4"))
        self.press("F4")
        self.assertIsNone(self.controller.state.mode)
        self.assertFalse(self.led("F4"))

    def test_new_and_shift_replace_each_other(self):
        self.press("F4")
        self.press("F3")
        self.assertEqual(self.controller.state.mode, SHIFT)
        self.assertFalse(self.led("F4"))
        self.press("F4")
        self.assertEqual(self.controller.state.mode, NEW)
        self.assertFalse(self.led("F3"))

    def test_new_browse_opens_the_add_menu(self):
        self.press("F4")
        self.press("BROWSE")
        self.assertEqual(transport.calls, [("globalTransport", midi.FPT_Menu, 1)])
        self.assertIsNone(self.controller.state.mode)
        del transport.calls[:]
        ui.in_popup_menu = True
        for _ in range(5):
            script.OnIdle()
        self.assertEqual(transport.calls, [("globalTransport", midi.FPT_Right, 1)] * 3)

    def test_queued_menu_commands_wait_for_the_menu_and_then_give_up(self):
        self.press("F4")
        self.press("BROWSE")
        del transport.calls[:]
        for _ in range(ui_commands.MENU_WAIT_TICKS):
            script.OnIdle()
        self.assertEqual(transport.calls, [])
        ui.in_popup_menu = True
        script.OnIdle()
        self.assertEqual(transport.calls, [])  # queue dropped: the menu never opened in time

    def test_new_pattern_starts_a_new_pattern_once(self):
        self.press("F4")
        self.press("PATTERN")
        self.assertEqual(patterns.calls, [("findFirstNextEmptyPat", midi.FFNEP_DontPromptName)])
        self.assertIsNone(self.controller.state.mode)

    def test_controls_without_a_new_function_act_normally_and_keep_new_mode(self):
        self.press("F4")
        self.press("PLAY")
        self.assertEqual(transport.calls, [("start",)])
        self.assertEqual(self.controller.state.mode, NEW)

    def test_new_mode_lights(self):
        self.press("F4")
        for control_id in ("F4", "BROWSE", "PATTERN", "ALL"):
            self.assertTrue(self.led(control_id), control_id)
        for control_id in ("F3", "F5", "PLAY", "RESTART"):
            self.assertFalse(self.led(control_id), control_id)
        for control_id in PAD_IDS + GROUP_IDS:
            self.assertEqual(self.led(control_id), colors.OFF, control_id)

    def test_new_all_saves_a_new_version_once(self):
        self.press("F4")
        self.press("ALL")
        self.assertEqual(transport.calls, [("globalTransport", midi.FPT_SaveNew, 1)])
        self.assertIsNone(self.controller.state.mode)

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
        script.OnMidiMsg(cc(controls.BY_ID["F3"].number))
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
            script.OnMidiMsg(cc(controls.BY_ID["F5"].number))
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
        self.send(cc(controls.BY_ID["F15"].number))
        event = self.send(note_on(controls.BY_ID["PAD_1"].number, 30))
        self.assertEqual((event.data1, event.data2), (36, 127))

    def test_leaving_fpc_restores_chromatic_layout(self):
        self.select_fpc()
        self.select_channel(0)
        self.assertEqual(self.send(note_on(controls.BY_ID["PAD_1"].number)).data1, 64)  # Group E, chromatic
        self.assertEqual(self.pad_leds()["PAD_1"], RED)



class KeyboardModeTest(ScriptTestCase):
    """Keyboard pad mode: chromatic notes on every channel, pads lit as piano keys."""

    select_fpc = FpcModeTest.select_fpc
    select_channel = FpcModeTest.select_channel
    pad_leds = FpcModeTest.pad_leds

    def setUp(self):
        super().setUp()
        self.send(cc(controls.BY_ID["PAD_MODE"].number))
        self.send(cc(controls.BY_ID["ENCODER"].number, 1))  # Keyboard
        self.send(cc(controls.BY_ID["PAD_MODE"].number, 0))  # override off
        self.assertEqual(self.controller.state.pad_mode, KEYBOARD)

    def test_hint_has_no_placeholder_note(self):
        self.assertIn("Pad mode: Keyboard", ui.hints)

    def test_pads_play_the_groups_chromatic_notes(self):
        pad_13 = controls.BY_ID["PAD_13"].number
        event = self.send(note_on(pad_13, 40))
        self.assertFalse(event.handled)
        self.assertEqual((event.data1, event.data2), (60, 40))  # Group D: middle C
        self.send(cc(controls.BY_ID["GROUP_B"].number))
        self.assertEqual(self.send(FakeEvent(midi.MIDI_KEYAFTERTOUCH, pad_13, 55)).data1, 60)  # still held
        self.assertEqual(self.send(note_off(pad_13)).data1, 60)  # the sounding note
        self.assertEqual(self.send(note_on(pad_13)).data1, 28)  # Group B

    def test_fixed_velocity_applies(self):
        self.send(cc(controls.BY_ID["F15"].number))
        self.assertEqual(self.send(note_on(controls.BY_ID["PAD_1"].number, 30)).data2, 127)

    def test_pads_are_lit_as_piano_keys(self):
        leds = self.pad_leds()
        dim_red = (0, 127, renderer.BLACK_KEY_BRIGHTNESS)
        self.assertEqual(leds["PAD_1"], colors.WHITE)  # 48, C
        self.assertEqual(leds["PAD_2"], dim_red)  # C#
        self.assertEqual(leds["PAD_3"], RED)  # D
        self.assertEqual(leds["PAD_13"], colors.WHITE)  # 60, middle C
        self.assertEqual(leds["PAD_14"], dim_red)  # C#
        self.assertEqual(leds["PAD_15"], RED)  # D
        for index, pad in enumerate(controls.PADS):
            note = 48 + index
            expected = colors.WHITE if note % 12 == 0 else dim_red if note % 12 in (1, 3, 6, 8, 10) else RED
            self.assertEqual(leds[pad.id], expected, pad.id)

    def test_fpc_is_played_and_lit_chromatically(self):
        self.select_fpc()
        self.assertEqual(self.controller.state.pad_group, 3)  # no jump to Group E
        self.assertEqual(self.send(note_on(controls.BY_ID["PAD_1"].number)).data1, 48)  # not FPC's 36
        self.send(note_off(controls.BY_ID["PAD_1"].number))
        self.assertEqual(self.pad_leds()["PAD_2"], (42, 127, renderer.BLACK_KEY_BRIGHTNESS))  # green channel, C#
        for letter in "ABCDEFGH":
            self.assertNotEqual(self.controller.leds._sent["GROUP_" + letter], colors.OFF)

    def test_back_to_default_on_an_fpc_jumps_to_its_banks(self):
        self.select_fpc()
        self.send(cc(controls.BY_ID["PAD_MODE"].number))
        self.send(cc(controls.BY_ID["ENCODER"].number, 0x7F))  # Default
        self.assertEqual(self.controller.state.pad_mode, DEFAULT_PADS)
        self.assertEqual(self.controller.state.pad_group, 4)
        self.assertEqual(self.send(note_on(controls.BY_ID["PAD_1"].number)).data1, 36)

    def test_shift_pads_still_override(self):
        self.send(cc(controls.BY_ID["F3"].number))
        self.assertTrue(self.send(note_on(controls.BY_ID["PAD_1"].number)).handled)
        self.assertIn("undoUp", general.calls)
        self.assertEqual(self.pad_leds()["PAD_1"], colors.ORANGE)


if __name__ == "__main__":
    unittest.main()
