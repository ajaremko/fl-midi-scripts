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
from ..handlers import sequencer
from ..handlers.channel_colors import PALETTE
from ..state import CHANNELS, COLOR, KEYBOARD, NEW, PADS, SEQUENCER, SHIFT
from . import colors

# Brightness of the pads and the selected Group button. Full brightness keeps dark channel
# colours visible; the hue and saturation still match FL Studio.
LIT_BRIGHTNESS = colors.MAX
# Brightness of the Group buttons that are not selected.
DIM_BRIGHTNESS = 24
# Color mode: palette pads other than the selected channel's current colour.
PALETTE_DIM = 70
# Keyboard pad mode: black-key pads, in the channel's colour. Brighter than DIM_BRIGHTNESS because
# pads look dimmer than the Group buttons; tune on the hardware.
BLACK_KEY_BRIGHTNESS = 20
# Sequencer pad mode: steps that are off, in the channel's colour. Tune on the hardware.
STEP_OFF_BRIGHTNESS = 20
# Channels pad mode: channels that aren't selected, in their own colour (Color mode dims the same).
CHANNEL_DIM_BRIGHTNESS = 70

_PAD_IDS = [control.id for control in controls.PADS]


def _channel_hsb(fl):
    """The selected channel's colour as HSB, or white when no channel is selected."""
    return (
        colors.rgb_to_hsb(fl.channel_color)
        if fl.channel_color is not None
        else colors.WHITE
    )


def _channel_color(state, fl, frame):
    """Pads and Group buttons take the selected channel's colour; the selected group is brightest.

    While the selected channel is FPC (in Pads mode), only the FPC groups light, and the pads
    take the colours of FPC's pads (empty pads stay dark).
    """
    color = _channel_hsb(fl)
    lit = colors.with_brightness(color, LIT_BRIGHTNESS)
    fpc_mode = fl.fpc_channel is not None and state.pad_mode == PADS

    if not fpc_mode:
        for pad_id in _PAD_IDS:
            frame[pad_id] = lit
    else:
        bank = notes.FPC_BANK_FOR_GROUP.get(state.pad_group)
        if bank is not None:
            for pad_id, fpc_pad in zip(_PAD_IDS, fl.fpc_banks[bank]):
                if not fpc_pad.empty:
                    frame[pad_id] = colors.with_brightness(
                        colors.rgb_to_hsb(fpc_pad.color), LIT_BRIGHTNESS
                    )

    for index, letter in enumerate("ABCDEFGH"):
        if fpc_mode and index not in notes.FPC_BANK_FOR_GROUP:
            continue
        frame["GROUP_" + letter] = (
            lit
            if index == state.pad_group
            else colors.with_brightness(color, DIM_BRIGHTNESS)
        )


# The button that focuses each window, lit while that window is focused.
WINDOW_BUTTONS = {
    midi.widBrowser: "BROWSE",
    midi.widChannelRack: "F5",
    midi.widPianoRoll: "F6",
    midi.widPlaylist: "F7",
    midi.widMixer: "F8",
}


def _focused_window(state, fl, frame):
    button = WINDOW_BUTTONS.get(fl.focused_window)
    if button:
        frame[button] = True


def _transport(state, fl, frame):
    frame["PLAY"] = fl.playing
    frame["REC"] = fl.recording
    frame["SCENE"] = fl.song_mode


def _channel_state(state, fl, frame):
    """Solo and Mute light while the selected channel is soloed or muted."""
    frame["SOLO"] = fl.channel_solo
    frame["MUTE"] = fl.channel_muted


def _pad_layer(state, fl, frame):
    """Pads the pad mode's layer binds to a placeholder (Keyboard and Sequencer, until they're
    written) stay dark. Pad Mode itself lights through _encoder_mode while its override is on.
    """
    layer = bindings.LAYERS[state.pad_mode]
    for pad_id in _PAD_IDS:
        if getattr(layer.get(pad_id), "placeholder", False):
            frame[pad_id] = colors.OFF


def _keyboard_pads(state, fl, frame):
    """Keyboard pad mode: each pad by its note's key. C white, the other white keys the channel
    colour, black keys the channel colour at BLACK_KEY_BRIGHTNESS."""
    if state.pad_mode != KEYBOARD:
        return
    color = _channel_hsb(fl)
    for index, pad_id in enumerate(_PAD_IDS):
        note = notes.pad_note(state.pad_group, index)
        if notes.is_c(note):
            frame[pad_id] = colors.WHITE
        elif notes.is_black_key(note):
            frame[pad_id] = colors.with_brightness(color, BLACK_KEY_BRIGHTNESS)
        else:
            frame[pad_id] = colors.with_brightness(color, LIT_BRIGHTNESS)


def _playhead_offset(state, fl):
    """The step (0-15) of the pads' page that FL is playing, or None. Only while FL plays in pattern
    mode (in song mode its step position isn't the pattern's), and only inside the pattern, as
    Novation's script checks."""
    if not fl.playing or fl.song_mode or not 0 <= fl.step_pos < fl.pattern_steps:
        return None
    page, offset = divmod(fl.step_pos, sequencer.STEPS_PER_PAGE)
    return offset if page == state.step_page else None


def _sequencer_pads(state, fl, frame):
    """Sequencer pad mode. Each pad is a step of the page (sequencer.STEP_FOR_PAD, reading order):
    the channel's colour when on, STEP_OFF_BRIGHTNESS of it when off, white under the playhead;
    dark without a channel or a step grid. The Group buttons are the pages: the pads' page bright,
    the pattern's other pages dim, pages past the pattern's end dark."""
    if state.pad_mode != SEQUENCER:
        return
    color = _channel_hsb(fl)
    pattern_pages = max(1, -(-fl.pattern_steps // sequencer.STEPS_PER_PAGE))  # rounded up
    for index, letter in enumerate("ABCDEFGH"):
        if index == state.step_page:
            frame["GROUP_" + letter] = colors.with_brightness(color, LIT_BRIGHTNESS)
        elif index < pattern_pages:
            frame["GROUP_" + letter] = colors.with_brightness(color, DIM_BRIGHTNESS)
        else:
            frame["GROUP_" + letter] = colors.OFF

    if fl.step_channel is None or not fl.grid_assigned:
        for pad_id in _PAD_IDS:
            frame[pad_id] = colors.OFF
        return
    playhead = _playhead_offset(state, fl)
    for pad_id, step in zip(_PAD_IDS, sequencer.STEP_FOR_PAD):
        if step == playhead:
            frame[pad_id] = colors.WHITE
        elif fl.steps[step]:
            frame[pad_id] = colors.with_brightness(color, LIT_BRIGHTNESS)
        else:
            frame[pad_id] = colors.with_brightness(color, STEP_OFF_BRIGHTNESS)


def _channel_pads(state, fl, frame):
    """Channels pad mode. Pad i (pad-number order) is channel channel_offset + i, in that channel's
    colour: full brightness when selected, CHANNEL_DIM_BRIGHTNESS when not, dark past the last
    channel. Group buttons: the divisions the 16 pads overlap bright, other divisions with
    channels dim, divisions past the last channel dark."""
    if state.pad_mode != CHANNELS:
        return
    for pad_id, rgb, selected in zip(_PAD_IDS, fl.rack_colors, fl.rack_selected):
        if rgb is None:
            frame[pad_id] = colors.OFF
        else:
            brightness = LIT_BRIGHTNESS if selected else CHANNEL_DIM_BRIGHTNESS
            frame[pad_id] = colors.with_brightness(colors.rgb_to_hsb(rgb), brightness)

    color = _channel_hsb(fl)
    shown_last = min(state.channel_offset + len(_PAD_IDS), fl.channel_count) - 1
    for index, letter in enumerate("ABCDEFGH"):
        first = index * len(_PAD_IDS)
        if first >= fl.channel_count:
            frame["GROUP_" + letter] = colors.OFF
        elif first <= shown_last and state.channel_offset <= first + len(_PAD_IDS) - 1:
            frame["GROUP_" + letter] = colors.with_brightness(color, LIT_BRIGHTNESS)
        else:
            frame["GROUP_" + letter] = colors.with_brightness(color, DIM_BRIGHTNESS)


def _pad_mode(state, fl, frame):
    frame["F15"] = state.fixed_velocity
    frame["NOTE_REPEAT"] = bool(
        state.note_repeat
    )  # lit in On and Triplets; only ever on in bridge mode


def _encoder_mode(state, fl, frame):
    # Override modes are named after the buttons that toggle them.
    if state.encoder_mode:
        frame[state.encoder_mode] = True


# The button that toggles each global mode, lit while that mode is on.
MODE_BUTTONS = {
    SHIFT: ("F3", "F11"),
    NEW: ("F4",),
    COLOR: ("F12",),
}  # all lit while the mode is on


# The colour of each highlighted RGB control in a mode, grouped by function. Controls not listed
# keep the channel colour.
MODE_COLORS = {
    SHIFT: {
        "PAD_1": colors.ORANGE,  # undo
        "PAD_2": colors.ORANGE,  # redo
        "PAD_3": colors.ORANGE,  # compare (undo toggle)
        "PAD_11": colors.CYAN,  # copy
        "PAD_12": colors.CYAN,  # paste
        "PAD_5": colors.GREEN,  # quantize
        "PAD_7": colors.BLUE,  # nudge left (tempo)
        "PAD_8": colors.BLUE,  # nudge right (tempo)
        "PAD_9": colors.RED,  # clear (delete)
        "PAD_10": colors.YELLOW,  # cut
        "PAD_13": colors.PURPLE,  # semitone up
        "PAD_14": colors.PURPLE,  # semitone down
        "PAD_15": colors.PURPLE,  # octave down
        "PAD_16": colors.PURPLE,  # octave up
    },
}


def _color_mode_pads(fl):
    """Color mode: each pad in its palette colour, the selected channel's current one brightest."""
    current = fl.channel_color
    return {
        pad_id: colors.with_brightness(
            colors.rgb_to_hsb(color),
            LIT_BRIGHTNESS if color == current else PALETTE_DIM,
        )
        for pad_id, color in zip(_PAD_IDS, PALETTE)
    }


def _mode_highlight(state, fl, frame):
    """While Shift, New or Color mode is on, light only its button and the controls with a function
    in it. Color mode lights the pads in its palette (_color_mode_pads).

    Must stay the last rule: it replaces what the earlier rules showed until the mode turns off.
    """
    if not state.mode:
        return
    mode_controls = bindings.MODE_CONTROLS[state.mode]
    mode_colors = (
        _color_mode_pads(fl) if state.mode == COLOR else MODE_COLORS.get(state.mode, {})
    )
    lit_hsb = colors.with_brightness(_channel_hsb(fl), LIT_BRIGHTNESS)
    for control in controls.LED_CONTROLS:
        shown = control.id in MODE_BUTTONS[state.mode] or control.id in mode_controls
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
    _pad_layer,
    _keyboard_pads,
    _sequencer_pads,
    _channel_pads,
    _focused_window,
    _transport,
    _channel_state,
    _pad_mode,
    _encoder_mode,
    _mode_highlight,
]


def render(state, fl):
    frame = {}
    for rule in RULES:
        rule(state, fl, frame)
    return frame
