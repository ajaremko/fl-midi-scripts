"""
Master encoder.

Turning navigates whatever is focused: an open popup menu first, otherwise the focused window
(up/down, or left/right in the mixer). Pushing does that window's action. Volume, Swing, Tempo,
Navigate, Pattern and Grid toggle an override mode; while one is on, turning adjusts master volume,
swing or tempo, or jogs between windows, patterns or snap settings, instead.
Entering Shift or New mode turns the override off (see modes.toggle).
"""

import channels
import midi
import mixer
import transport
import ui

from .. import events
from .common import on_press

VOLUME_STEP = 0.05  # master volume, 0-1, per encoder step
SWING_STEP = 10  # FPT_ShuffleJog units per encoder step
TEMPO_STEP = 10  # FPT_TempoJog units (0.1 BPM) per encoder step: 1 BPM


def _volume(delta):
    volume = mixer.getTrackVolume(0) + delta * VOLUME_STEP  # track 0 is the master track
    mixer.setTrackVolume(0, min(1.0, max(0.0, volume)))


def _swing(delta):
    transport.globalTransport(midi.FPT_ShuffleJog, delta * SWING_STEP)


def _tempo(delta):
    transport.globalTransport(midi.FPT_TempoJog, delta * TEMPO_STEP)


def _jog(command):
    """An override that sends one jog step per encoder message, in the turn's direction."""

    def adjust(delta):
        transport.globalTransport(command, -1 if delta < 0 else 1)

    return adjust


# Override mode -> what a turn adjusts. Mode names are the ids of the buttons that toggle them,
# so the renderer can light the active one.
MODES = {
    "VOLUME": _volume,
    "SWING": _swing,
    "TEMPO": _tempo,
    "NAVIGATE": _jog(midi.FPT_WindowJog),  # between open windows
    "PATTERN": _jog(midi.FPT_PatternJog),  # through patterns
    "GRID": _jog(midi.FPT_SnapMode),  # through main snap settings
}


def toggle_mode(mode):
    """Turn an override mode on, or off if it is already on."""

    @on_press
    def handler(controller, ev):
        state = controller.state
        state.encoder_mode = None if state.encoder_mode == mode else mode

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


def _open_channel():
    transport.globalTransport(midi.FPT_Insert, 1)
    channels.focusEditor(channels.selectedChannel())


# Push: what pressing the encoder does.
MENU_PUSH = _command(midi.FPT_Enter)
PUSH = {
    midi.widMixer: _command(midi.FPT_Menu),
    midi.widChannelRack: _open_channel,
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
    adjust = MODES.get(controller.state.encoder_mode)
    if adjust is None:
        _navigate(ev.delta)
    else:
        adjust(ev.delta)


@on_press
def push(controller, ev):
    if ui.isInPopupMenu():
        MENU_PUSH()
        return
    action = PUSH.get(_focused_window())
    if action is not None:
        action()
