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
    channel_colors,
    channel_controls,
    channel_knobs,
    channel_pads,
    macro_knobs,
    mixer_pads,
    mixer_tracks,
    edit,
    encoder,
    groups,
    modes,
    note_repeat,
    pad_modes,
    pads,
    pattern_controls,
    presets,
    sequencer,
    transport_controls,
    ui_commands,
    windows,
)
from .state import BASE, CHANNELS, COLOR, KEYBOARD, MIXER, NEW, PADS, SEQUENCER, SHIFT

_base = {
    # Top
    # Control and Step both switch pattern / song playback; their labels don't match (Control is lit
    # in song mode, Step in pattern mode).
    "CONTROL": transport_controls.toggle_song_mode,
    "STEP": transport_controls.toggle_song_mode,
    "BROWSE": windows.toggle(midi.widBrowser),
    "SAMPLING": unimplemented(),
    "ALL": unimplemented(),
    "AUTO": unimplemented(),
    # Function buttons, page 1
    "F1": ui_commands.send(midi.FPT_Menu),  # Menu
    "F2": ui_commands.send(midi.FPT_Escape),  # Esc
    "F3": modes.toggle(SHIFT),  # Shift
    "F4": modes.toggle(NEW),  # New
    "F5": windows.toggle(midi.widChannelRack),  # Channels
    "F6": windows.toggle(midi.widPianoRoll),  # Piano Roll
    "F7": windows.toggle(midi.widPlaylist),  # Playlist
    "F8": windows.toggle(midi.widMixer),  # Mixer
    # Function buttons, page 2
    "F9": ui_commands.send(midi.FPT_ItemMenu),  # Alt Menu
    "F10": ui_commands.send(midi.FPT_Escape),  # Esc (again)
    "F11": modes.toggle(SHIFT),  # Shift (again)
    "F12": modes.toggle(COLOR),  # Color
    "F13": presets.step(-1),  # Previous preset
    "F14": presets.step(+1),  # Next preset
    "F15": pads.toggle_fixed_velocity,  # Fixed velocity
    "F16": mixer_tracks.assign_free_track,  # Auto mixer track
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
    "SCENE": encoder.toggle_mode("SCENE"),  # the pattern override: the encoder picks the pattern
    "PATTERN": encoder.toggle_mode("PATTERN", hint=pattern_controls.show_length),  # pattern length
    "PAD_MODE": encoder.toggle_mode("PAD_MODE", hint=pad_modes.show),  # the pad mode override
    "NAVIGATE": encoder.toggle_mode("NAVIGATE"),
    "DUPLICATE": pattern_controls.duplicate_pattern,
    "SELECT": unimplemented(),
    "SOLO": channel_controls.solo,
    "MUTE": channel_controls.mute,
}

# E1-E8: the selected channel's settings. E9-E16 (knob page 2): macros for the focused plugin.
for _i in (1, 2, 3, 5, 6, 7):
    _base["E%d" % _i] = channel_knobs.turn
_base["E4"] = channel_knobs.pitch_range
_base["E8"] = channel_knobs.mixer_track
for _i in range(9, 17):
    _base["E%d" % _i] = macro_knobs.turn

for _index, _letter in enumerate("ABCDEFGH"):
    _base["GROUP_" + _letter] = groups.select(_index)

# Pads play the selected channel, at the notes of the selected pad group.
for _i in range(1, 17):
    _base["PAD_%d" % _i] = pads.play

_shift = {
    "BROWSE": ui_commands.send(midi.FPT_F8),  # plugin picker
    "ALL": ui_commands.send(midi.FPT_Save),  # Save
    "NOTE_REPEAT": ui_commands.send(midi.FPT_TapTempo),  # Tap
    "RESTART": ui_commands.send(midi.FPT_LoopRecord),  # Loop: toggle loop recording
    "SELECT": channel_controls.open_piano_roll,  # Events
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
    "SCENE": modes.once(pattern_controls.new_pattern),
    "ALL": modes.once(ui_commands.send(midi.FPT_SaveNew)),  # save new version
}

# Color mode is latched like Shift: each pad colours the selected channel(s), and it stays on.
_color = {"PAD_%d" % (_i + 1): channel_colors.pick(_i) for _i in range(16)}

# Pad modes (handlers/pad_modes.py): searched between the global mode's layer and base, so each
# replaces only what it binds. Channels' pads play and select Channel Rack channels, and its Group
# buttons jump the focus. Pads binds nothing: the base layer's pads are Pads mode. Keyboard plays the
# chromatic layout on every channel (no FPC banks). Sequencer's pads toggle steps of the selected
# channel, and its Group buttons pick the page of steps. Mixer's pads are 4 mixer tracks' select,
# mute, arm and routing pads, and its Group buttons jump by blocks of used tracks.
_channels_pads = {"PAD_%d" % (_i + 1): channel_pads.play(_i) for _i in range(16)}
for _index, _letter in enumerate("ABCDEFGH"):
    _channels_pads["GROUP_" + _letter] = channel_pads.jump(_index)
_pads_layer = {}
_keyboard_pads = {"PAD_%d" % (_i + 1): pads.play_keyboard for _i in range(16)}
_sequencer_pads = {"PAD_%d" % (_i + 1): sequencer.toggle_step(_i) for _i in range(16)}
for _index, _letter in enumerate("ABCDEFGH"):
    _sequencer_pads["GROUP_" + _letter] = sequencer.select_page(_index)
_mixer_pads = {"PAD_%d" % (_i + 1): mixer_pads.pad(_i) for _i in range(16)}
for _index, _letter in enumerate("ABCDEFGH"):
    _mixer_pads["GROUP_" + _letter] = mixer_pads.jump(_index)

LAYERS = {
    BASE: _base,
    SHIFT: _shift,
    NEW: _new,
    COLOR: _color,
    CHANNELS: _channels_pads,
    PADS: _pads_layer,
    KEYBOARD: _keyboard_pads,
    SEQUENCER: _sequencer_pads,
    MIXER: _mixer_pads,
}

def _implemented(layer):
    """The controls in a layer bound to a real function, not an unimplemented(...) placeholder."""
    return frozenset(control_id for control_id, handler in layer.items() if not getattr(handler, "placeholder", False))


# Controls that do something different in each mode. While a mode is on, the renderer lights
# only these (and the mode's button).
MODE_CONTROLS = {
    SHIFT: _implemented(_shift),
    NEW: _implemented(_new),
    COLOR: _implemented(_color),
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


def pads_play_notes(state):
    """Whether the MK2 bridge should treat the pads as notes and repeat them: no global mode is on
    (as before pad modes; New mode's unbound pads still play but aren't repeated), and the pad
    mode's pads play notes (handlers marked plays_notes, such as pads.play and play_keyboard)."""
    return state.mode is None and all(getattr(lookup(state, "PAD_%d" % (i + 1)), "plays_notes", False)
                                      for i in range(16))
