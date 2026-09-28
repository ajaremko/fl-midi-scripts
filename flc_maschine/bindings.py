"""
Function configuration: which handler each control runs, per layer.

The dispatcher searches the layers returned by ControllerState.active_layers() in order, so a
control with no entry in the shift layer falls back to its base binding. A control with no
binding in any active layer is logged and passed to FL Studio (the E1-E16 knobs rely on this so
they can be linked to plugin parameters with FL's "Link to controller").

The descriptions come from the README's Control Functionality table; replace each
unimplemented(...) with a real handler as the feature is written.
"""

import midi

from .handlers.common import unimplemented
from .handlers import groups, modes, pads, transport_controls, windows
from .state import BASE, SHIFT

_base = {
    # Top
    "CONTROL": unimplemented(),
    "STEP": unimplemented(),
    "BROWSE": windows.toggle(midi.widBrowser),
    "SAMPLING": unimplemented(),
    "ALL": unimplemented(),
    "AUTO": unimplemented(),
    "F1": windows.toggle(midi.widChannelRack),
    "F2": windows.toggle(midi.widPianoRoll),
    "F3": windows.toggle(midi.widPlaylist),
    "F4": windows.toggle(midi.widMixer),
    "F5": modes.toggle_shift,
    # Master
    "VOLUME": unimplemented("hold + turn encoder to adjust master volume"),
    "SWING": unimplemented("hold + turn encoder to adjust master swing"),
    "TEMPO": unimplemented("hold + turn encoder to adjust master tempo"),
    "MASTER_LEFT": unimplemented(),
    "MASTER_RIGHT": unimplemented(),
    "ENTER": unimplemented("enter"),
    "NOTE_REPEAT": unimplemented(),
    "ENCODER": unimplemented("navigate up/down in current screen"),
    "ENCODER_PUSH": unimplemented("enter"),
    # Transport
    "RESTART": transport_controls.restart,
    "STEP_LEFT": transport_controls.step_left,
    "STEP_RIGHT": transport_controls.step_right,
    "GRID": unimplemented(),
    "PLAY": transport_controls.play,
    "REC": transport_controls.record,
    "ERASE": unimplemented(),
    # Pads area buttons
    "SCENE": unimplemented(),
    "PATTERN": unimplemented(),
    "PAD_MODE": unimplemented(),
    "NAVIGATE": unimplemented(),
    "DUPLICATE": unimplemented(),
    "SELECT": unimplemented(),
    "SOLO": unimplemented(),
    "MUTE": unimplemented(),
}

# F6-F16 have no function yet.
for _i in range(6, 17):
    _base["F%d" % _i] = unimplemented()

for _index, _letter in enumerate("ABCDEFGH"):
    _base["GROUP_" + _letter] = groups.select(_index)

# Pads play the selected channel, at the notes of the selected pad group.
for _i in range(1, 17):
    _base["PAD_%d" % _i] = pads.play

_shift = {
    "ALL": unimplemented("save project"),
    "PLAY": transport_controls.metronome,
    "REC": transport_controls.count_in,
    # Pads become edit actions.
    "PAD_1": unimplemented("undo"),
    "PAD_2": unimplemented("redo"),
    "PAD_3": unimplemented("step undo"),
    "PAD_4": unimplemented("step redo"),
    "PAD_5": unimplemented("quantize selection"),
    "PAD_6": unimplemented("quantize selection 50%"),
    "PAD_7": unimplemented("nudge left"),
    "PAD_8": unimplemented("nudge right"),
    "PAD_9": unimplemented("delete"),
    "PAD_10": unimplemented("clear automation"),
    "PAD_11": unimplemented("copy"),
    "PAD_12": unimplemented("paste"),
    "PAD_13": unimplemented("decrease midi offset 1 step"),
    "PAD_14": unimplemented("increase midi offset 1 step"),
    "PAD_15": unimplemented("increase midi offset 12 steps"),
    "PAD_16": unimplemented("decrease midi offset 12 steps"),
}

LAYERS = {
    BASE: _base,
    SHIFT: _shift,
}


def lookup(state, control_id):
    """Return the handler for control_id in the highest-priority active layer, or None."""
    for layer in state.active_layers():
        handler = LAYERS[layer].get(control_id)
        if handler is not None:
            return handler
    return None
