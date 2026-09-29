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
from .handlers import (
    channel_controls,
    edit,
    encoder,
    groups,
    modes,
    note_repeat,
    pads,
    pattern_controls,
    transport_controls,
    ui_commands,
    windows,
)
from .state import BASE, NEW, SHIFT

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
    "F5": ui_commands.send_for_focus(
        midi.FPT_Menu,
        {
            midi.widBrowser: midi.FPT_ItemMenu,
            midi.widPianoRoll: midi.FPT_ItemMenu,
        },
    ),
    "F6": ui_commands.send(midi.FPT_Escape),
    "F7": modes.toggle(NEW),
    "F8": modes.toggle(SHIFT),
    # Master
    "VOLUME": encoder.toggle_mode("VOLUME"),
    "SWING": encoder.toggle_mode("SWING"),
    "TEMPO": encoder.toggle_mode("TEMPO"),
    "MASTER_LEFT": ui_commands.send(midi.FPT_Left),
    "MASTER_RIGHT": ui_commands.send(midi.FPT_Right),
    "ENTER": ui_commands.enter,
    "NOTE_REPEAT": unimplemented(),
    "ENCODER": encoder.turn,
    "ENCODER_PUSH": encoder.push,
    # Transport
    "RESTART": transport_controls.restart,
    "STEP_LEFT": transport_controls.step_left,
    "STEP_RIGHT": transport_controls.step_right,
    "GRID": encoder.toggle_mode("GRID"),
    "PLAY": transport_controls.play,
    "REC": transport_controls.record,
    "ERASE": unimplemented(),
    # Pads area buttons
    "SCENE": transport_controls.toggle_song_mode,
    "PATTERN": encoder.toggle_mode("PATTERN"),
    "PAD_MODE": pads.toggle_fixed_velocity,
    "NAVIGATE": encoder.toggle_mode("NAVIGATE"),
    "DUPLICATE": pattern_controls.duplicate_pattern,
    "SELECT": unimplemented(),
    "SOLO": channel_controls.solo,
    "MUTE": channel_controls.mute,
}

# F9-F16 have no function yet.
for _i in range(9, 17):
    _base["F%d" % _i] = unimplemented()

for _index, _letter in enumerate("ABCDEFGH"):
    _base["GROUP_" + _letter] = groups.select(_index)

# Pads play the selected channel, at the notes of the selected pad group.
for _i in range(1, 17):
    _base["PAD_%d" % _i] = pads.play

_shift = {
    "BROWSE": ui_commands.send(midi.FPT_F8),  # plugin picker
    "ALL": unimplemented("save project"),
    "PLAY": transport_controls.metronome,
    "REC": transport_controls.count_in,
    # Pads become edit actions.
    "PAD_1": edit.undo,
    "PAD_2": edit.redo,
    "PAD_3": edit.compare,
    "PAD_4": unimplemented("split"),
    "PAD_5": edit.quantize,
    "PAD_6": unimplemented("quantize 50% (not possible: FL's quickQuantize has no strength setting)"),
    "PAD_7": ui_commands.send(midi.FPT_TempoJog, -1),  # nudge left: tempo -0.1 BPM
    "PAD_8": ui_commands.send(midi.FPT_TempoJog, +1),  # nudge right: tempo +0.1 BPM
    "PAD_9": ui_commands.send(midi.FPT_Delete),  # clear
    "PAD_10": ui_commands.send(midi.FPT_Cut),  # cut, on the Clear Auto pad
    "PAD_11": ui_commands.send(midi.FPT_Copy),
    "PAD_12": ui_commands.send(midi.FPT_Paste),
    "PAD_13": pads.transpose(+1),  # semitone up
    "PAD_14": pads.transpose(-1),  # semitone down
    "PAD_15": pads.transpose(-12),  # octave down
    "PAD_16": pads.transpose(+12),  # octave up
}

# New mode is one-shot: each function turns New mode off after it runs.
_new = {
    # FL's Add menu (no API to add a channel): main menu, then Right x3.
    "BROWSE": modes.once(
        ui_commands.open_menu_then(midi.FPT_Menu, [midi.FPT_Right] * 3)
    ),
    "PATTERN": modes.once(pattern_controls.new_pattern),
}

LAYERS = {
    BASE: _base,
    SHIFT: _shift,
    NEW: _new,
}

def _implemented(layer):
    """The controls in a layer bound to a real function, not an unimplemented(...) placeholder."""
    return frozenset(control_id for control_id, handler in layer.items() if not getattr(handler, "placeholder", False))


# Controls that do something different in each mode. While a mode is on, the renderer lights
# only these (and the mode's button).
MODE_CONTROLS = {
    SHIFT: _implemented(_shift),
    NEW: _implemented(_new),
}


# Base-layer functions that only exist with the MK2 bridge (the Bridge entry script). They take
# the place of the base layer's placeholders when the controller runs in bridge mode.
BRIDGE_BASE = {
    "NOTE_REPEAT": note_repeat.toggle,
}


def lookup(state, control_id, bridge=False):
    """Return the handler for control_id in the highest-priority active layer, or None."""
    for layer in state.active_layers():
        handler = BRIDGE_BASE.get(control_id) if bridge and layer == BASE else None
        if handler is None:
            handler = LAYERS[layer].get(control_id)
        if handler is not None:
            return handler
    return None
