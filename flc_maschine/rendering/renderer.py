"""
Decides what every LED should show, from the controller state and an FlSnapshot.

render() returns a frame: a dict of control id -> desired LED value. Mono LEDs take True/False;
HSB colour LEDs take a (hue, saturation, brightness) tuple of 0-127 values (see colors.py).
Controls missing from the frame are switched off. The frame is only a description;
output.LedWriter sends it.

To light something new, add a rule: a function rule(state, fl, frame) that sets frame entries,
and append it to RULES. Later rules override earlier ones.
"""

import midi

from .. import bindings, controls, notes
from ..state import NEW, SHIFT
from . import colors

# Brightness of the pads and the selected Group button. Full brightness keeps dark channel
# colours visible; the hue and saturation still match FL Studio.
LIT_BRIGHTNESS = colors.MAX
# Brightness of the Group buttons that are not selected.
DIM_BRIGHTNESS = 24

_PAD_IDS = [control.id for control in controls.PADS]


def _channel_hsb(fl):
    """The selected channel's colour as HSB, or white when no channel is selected."""
    return colors.rgb_to_hsb(fl.channel_color) if fl.channel_color is not None else colors.WHITE


def _channel_color(state, fl, frame):
    """Pads and Group buttons take the selected channel's colour; the selected group is brightest.

    While the selected channel is FPC, only the FPC groups light, and the pads take the colours
    of FPC's pads (empty pads stay dark).
    """
    color = _channel_hsb(fl)
    lit = colors.with_brightness(color, LIT_BRIGHTNESS)
    fpc_mode = fl.fpc_channel is not None

    if not fpc_mode:
        for index, pad_id in enumerate(_PAD_IDS):
            # Dark when the transposed note is out of MIDI's range: the pad is silent then.
            if notes.pad_note(state.pad_group, index, state.note_offset) is not None:
                frame[pad_id] = lit
    else:
        bank = notes.FPC_BANK_FOR_GROUP.get(state.pad_group)
        if bank is not None:
            for pad_id, fpc_pad in zip(_PAD_IDS, fl.fpc_banks[bank]):
                if not fpc_pad.empty:
                    frame[pad_id] = colors.with_brightness(colors.rgb_to_hsb(fpc_pad.color), LIT_BRIGHTNESS)

    for index, letter in enumerate("ABCDEFGH"):
        if fpc_mode and index not in notes.FPC_BANK_FOR_GROUP:
            continue
        frame["GROUP_" + letter] = lit if index == state.pad_group else colors.with_brightness(color, DIM_BRIGHTNESS)


# The button that focuses each window, lit while that window is focused.
WINDOW_BUTTONS = {
    midi.widBrowser: "BROWSE",
    midi.widChannelRack: "F1",
    midi.widPianoRoll: "F2",
    midi.widPlaylist: "F3",
    midi.widMixer: "F4",
}


def _focused_window(state, fl, frame):
    button = WINDOW_BUTTONS.get(fl.focused_window)
    if button:
        frame[button] = True


def _transport(state, fl, frame):
    frame["PLAY"] = fl.playing
    frame["REC"] = fl.recording
    frame["SCENE"] = fl.song_mode


def _pad_mode(state, fl, frame):
    frame["PAD_MODE"] = state.fixed_velocity


def _encoder_mode(state, fl, frame):
    # Override modes are named after the buttons that toggle them.
    if state.encoder_mode:
        frame[state.encoder_mode] = True


# The button that toggles each global mode, lit while that mode is on.
MODE_BUTTONS = {SHIFT: "F8", NEW: "F7"}


# The colour of each highlighted RGB control in a mode, grouped by function. Controls not listed
# keep the channel colour.
MODE_COLORS = {
    SHIFT: {
        "PAD_1": colors.ORANGE,  # undo
        "PAD_2": colors.ORANGE,  # redo
        "PAD_11": colors.BLUE,  # copy
        "PAD_12": colors.BLUE,  # paste
        "PAD_5": colors.GREEN,  # quantize
        "PAD_9": colors.RED,  # clear (cut)
        "PAD_13": colors.PURPLE,  # semitone down
        "PAD_14": colors.PURPLE,  # semitone up
        "PAD_15": colors.PURPLE,  # octave up
        "PAD_16": colors.PURPLE,  # octave down
    },
}


def _mode_highlight(state, fl, frame):
    """While Shift or New mode is on, light only its button and the controls with a function in it.

    Must stay the last rule: it replaces what the earlier rules showed until the mode turns off.
    """
    if not state.mode:
        return
    mode_controls = bindings.MODE_CONTROLS[state.mode]
    mode_colors = MODE_COLORS.get(state.mode, {})
    lit_hsb = colors.with_brightness(_channel_hsb(fl), LIT_BRIGHTNESS)
    for control in controls.LED_CONTROLS:
        shown = control.id == MODE_BUTTONS[state.mode] or control.id in mode_controls
        if fl.fpc_channel is not None and control.id in bindings.FPC_DISABLED:
            shown = False
        if control.led == controls.HSB:
            if not shown:
                frame[control.id] = colors.OFF
            elif control.id in mode_colors:
                frame[control.id] = mode_colors[control.id]
            elif frame.get(control.id, colors.OFF) == colors.OFF:
                frame[control.id] = lit_hsb  # e.g. pads that are dark in FPC mode
        else:
            frame[control.id] = shown


RULES = [
    _channel_color,
    _focused_window,
    _transport,
    _pad_mode,
    _encoder_mode,
    _mode_highlight,
]


def render(state, fl):
    frame = {}
    for rule in RULES:
        rule(state, fl, frame)
    return frame
