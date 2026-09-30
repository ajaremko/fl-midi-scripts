"""
Master encoder.

Turning navigates whatever is focused: an open popup menu first, otherwise the focused window
(up/down, or left/right in the mixer). Pushing does that window's action. Volume, Swing, Tempo,
Navigate, Pattern, Grid and Pad Mode toggle an override mode; while one is on, turning adjusts
master volume, swing or tempo, jogs between windows, patterns or snap settings, or picks the pad
mode (pad_modes.py), instead.
Entering Shift or New mode turns the override off (see modes.toggle).

Push and turn: turning while the encoder is pushed in selects a range of channels (Channel Rack) or
mixer tracks (Mixer); see selection.py. Elsewhere it turns as usual. The push's own action runs on
release, and only if the encoder wasn't turned while held, so a drag never also clicks. The
template's Push button must be in Gate mode for the release to arrive.
"""

import midi
import mixer
import transport
import ui

from .. import events
from . import channel_pads, note_repeat, pad_modes, selection
from .common import on_press

VOLUME_STEP = 0.05  # master volume, 0-1, per encoder step
SWING_STEP = 10  # FPT_ShuffleJog units per encoder step
TEMPO_STEP = 10  # FPT_TempoJog units (0.1 BPM) per encoder step: 1 BPM


def _volume(state, delta):
    volume = mixer.getTrackVolume(0) + delta * VOLUME_STEP  # track 0 is the master track
    mixer.setTrackVolume(0, min(1.0, max(0.0, volume)))


def _swing(state, delta):
    transport.globalTransport(midi.FPT_ShuffleJog, delta * SWING_STEP)


def _tempo(state, delta):
    transport.globalTransport(midi.FPT_TempoJog, delta * TEMPO_STEP)


def _jog(command):
    """An override that sends one jog step per encoder message, in the turn's direction."""

    def adjust(state, delta):
        transport.globalTransport(command, -1 if delta < 0 else 1)

    return adjust


# Override mode -> what a turn adjusts: adjust(state, delta). Mode names are the ids of the buttons
# that toggle them, so the renderer can light the active one.
MODES = {
    "VOLUME": _volume,
    "SWING": _swing,
    "TEMPO": _tempo,
    "NAVIGATE": _jog(midi.FPT_WindowJog),  # between open windows
    "PATTERN": _jog(midi.FPT_PatternJog),  # through patterns
    "GRID": _jog(midi.FPT_SnapMode),  # through main snap settings
    "PAD_MODE": pad_modes.step,  # Channels, Pads, Keyboard, Sequencer, Mixer
}


def toggle_mode(mode, hint=None):
    """Turn an override mode on, or off if it is already on. hint(state), if given, runs when it
    turns on, e.g. to show what the encoder will change."""

    @on_press
    def handler(controller, ev):
        state = controller.state
        state.encoder_mode = None if state.encoder_mode == mode else mode
        if hint is not None and state.encoder_mode == mode:
            hint(state)

    return handler


# Navigation: what a turn sends, as (counter-clockwise, clockwise) global transport commands.
MENU_NAVIGATION = (midi.FPT_Up, midi.FPT_Down)
NAVIGATION = {
    midi.widMixer: (midi.FPT_Left, midi.FPT_Right),
    midi.widChannelRack: (midi.FPT_Up, midi.FPT_Down),
    midi.widPlaylist: (midi.FPT_Up, midi.FPT_Down),
    midi.widPianoRoll: (midi.FPT_Up, midi.FPT_Down),
    midi.widBrowser: (midi.FPT_Up, midi.FPT_Down),
}


def _command(command):
    def send():
        transport.globalTransport(command, 1)

    return send


# Push: what pressing the encoder does.
MENU_PUSH = _command(midi.FPT_Enter)
PUSH = {
    midi.widMixer: _command(midi.FPT_Menu),
    midi.widChannelRack: _command(midi.FPT_ItemMenu),  # the selected channel's right-click menu
    midi.widPlaylist: _command(midi.FPT_Menu),
    midi.widPianoRoll: _command(midi.FPT_Menu),
    midi.widBrowser: _command(midi.FPT_Enter),
}


def _focused_window():
    """The focused window among those the encoder navigates, or None."""
    for window in NAVIGATION:
        if ui.getFocused(window):
            return window
    return None


def _navigate(delta):
    if ui.isInPopupMenu():
        commands = MENU_NAVIGATION
    else:
        commands = NAVIGATION.get(_focused_window())
        if commands is None:
            return
    counter_clockwise, clockwise = commands
    transport.globalTransport(counter_clockwise if delta < 0 else clockwise, 1)


def turn(controller, ev):
    if ev.kind != events.TURN:
        return
    state = controller.state
    if state.note_repeat:
        # While Note Repeat is on (bridge mode only), turning only changes its rate.
        if state.push_held:
            state.push_turned = True  # no click on release either
        note_repeat.step_rate(state, ev.delta)
        return
    if state.push_held:
        state.push_turned = True
        if selection.drag(state, ev.delta):  # takes priority over overrides and navigation
            return
    adjust = MODES.get(state.encoder_mode)
    if adjust is not None:
        adjust(state, ev.delta)
    elif channel_pads.scrolls(state):
        channel_pads.scroll(state, ev.delta)  # Channels mode in the Channel Rack: move the pads' focus
    else:
        _navigate(ev.delta)


def push(controller, ev):
    """Press: remember the encoder is held. Release: click (_click) unless it turned while held."""
    state = controller.state
    if ev.is_press:
        state.push_held = True
        state.push_turned = False
        state.drag_window = None
    elif ev.is_release:
        turned = state.push_turned
        state.push_held = False
        state.push_turned = False
        state.drag_window = None
        if not turned:
            _click()


def _click():
    if ui.isInPopupMenu():
        MENU_PUSH()
        return
    action = PUSH.get(_focused_window())
    if action is not None:
        action()
