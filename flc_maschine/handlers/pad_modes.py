"""
Pad modes, chosen with the master encoder while the Pad Mode override is on (encoder.MODES).

- Channels: each pad is a Channel Rack channel in its colour; a press plays C5 on it and selects
  it. The Group buttons and the encoder move the 16-channel focus (handlers/channel_pads.py).
- Pads (the startup mode): the pads play the selected group's notes in the channel's colour (FPC
  banks and colours on an FPC channel). The base layer's bindings.
- Keyboard: C white, other white keys in the channel's colour, black keys dimmer; plays like
  Pads, but chromatically on every channel (no FPC special case).
- Sequencer: the pads toggle the selected channel's steps, 16 at a time; the Group buttons pick
  the page (handlers/sequencer.py).
- Mixer: not written yet (placeholder pads, silent and dark).

Each pad mode has a binding layer (bindings.LAYERS), searched between the global mode (Shift, New,
Color) and base, so it only replaces what it binds. The choice stays after the override is off.
"""

import ui

from ..state import CHANNELS, KEYBOARD, MIXER, PAD_MODES, PADS, SEQUENCER

NAMES = {CHANNELS: "Channels", PADS: "Pads", KEYBOARD: "Keyboard", SEQUENCER: "Sequencer", MIXER: "Mixer"}

# Pad modes whose pads are still unimplemented(...) placeholders: silent and dark.
NOT_WRITTEN = (MIXER,)


def show(state):
    """Show the current pad mode in FL's hint bar."""
    suffix = " (not written yet)" if state.pad_mode in NOT_WRITTEN else ""
    ui.setHintMsg("Pad mode: %s%s" % (NAMES[state.pad_mode], suffix))


def step(state, delta):
    """The Pad Mode override's turn: the next or previous pad mode, one per encoder message,
    stopping at Channels and Mixer."""
    index = PAD_MODES.index(state.pad_mode) + (1 if delta > 0 else -1)
    state.pad_mode = PAD_MODES[max(0, min(len(PAD_MODES) - 1, index))]
    show(state)
