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

from .. import controls, notes
from . import colors

# Brightness of the pads and the selected Group button. Full brightness keeps dark channel
# colours visible; the hue and saturation still match FL Studio.
LIT_BRIGHTNESS = colors.MAX
# Brightness of the Group buttons that are not selected.
DIM_BRIGHTNESS = 24

_PAD_IDS = [control.id for control in controls.PADS]


def _channel_color(state, fl, frame):
    """Pads and Group buttons take the selected channel's colour; the selected group is brightest.

    While the selected channel is FPC, only the FPC groups light, and the pads take the colours
    of FPC's pads (empty pads stay dark).
    """
    color = colors.rgb_to_hsb(fl.channel_color) if fl.channel_color is not None else colors.WHITE
    lit = colors.with_brightness(color, LIT_BRIGHTNESS)
    fpc_mode = fl.fpc_channel is not None

    if not fpc_mode:
        for pad_id in _PAD_IDS:
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


def _shift_indicator(state, fl, frame):
    frame["F5"] = state.shift


RULES = [
    _channel_color,
    _focused_window,
    _transport,
    _shift_indicator,
]


def render(state, fl):
    frame = {}
    for rule in RULES:
        rule(state, fl, frame)
    return frame
