"""
Pad modes, chosen with the master encoder while the Pad Mode override is on (encoder.MODES).

- Default: the pads play the selected group's notes in the channel's colour (FPC banks and colours
  on an FPC channel). The base layer's bindings.
- Keyboard: C white, other white keys in the channel's colour, black keys dimmer; plays like
  Default, but chromatically on every channel (no FPC special case).
- Sequencer: the pads toggle the selected channel's steps, 16 at a time; the Group buttons pick
  the page (handlers/sequencer.py).

Each pad mode has a binding layer (bindings.LAYERS), searched between the global mode (Shift, New,
Color) and base, so it only replaces what it binds. The choice stays after the override is off.
"""

import ui

from ..state import DEFAULT_PADS, KEYBOARD, PAD_MODES, SEQUENCER

NAMES = {DEFAULT_PADS: "Default", KEYBOARD: "Keyboard", SEQUENCER: "Sequencer"}

# Pad modes whose pads are still unimplemented(...) placeholders: silent and dark. All three are
# written; a new pad mode can start here, with placeholders in its bindings layer.
NOT_WRITTEN = ()


def show(state):
    """Show the current pad mode in FL's hint bar."""
    suffix = " (not written yet)" if state.pad_mode in NOT_WRITTEN else ""
    ui.setHintMsg("Pad mode: %s%s" % (NAMES[state.pad_mode], suffix))


def step(state, delta):
    """The Pad Mode override's turn: the next or previous pad mode, one per encoder message,
    stopping at Default and Sequencer."""
    index = PAD_MODES.index(state.pad_mode) + (1 if delta > 0 else -1)
    state.pad_mode = PAD_MODES[max(0, min(len(PAD_MODES) - 1, index))]
    show(state)
