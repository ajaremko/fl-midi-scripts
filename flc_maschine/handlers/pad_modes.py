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
- Mixer: 4 mixer tracks, a column of pads each: select, mute, arm and routing; the Group buttons
  and the encoder move the focus (handlers/mixer_pads.py).

Each pad mode has a binding layer (bindings.LAYERS), searched between the global mode (Shift, New,
Color) and base, so it only replaces what it binds. The choice stays after the override is off.
"""

import midi
import ui

from ..state import CHANNELS, KEYBOARD, MIXER, PAD_MODES, PADS, SEQUENCER

NAMES = {CHANNELS: "Channels", PADS: "Pads", KEYBOARD: "Keyboard", SEQUENCER: "Sequencer", MIXER: "Mixer"}

# Pad modes whose pads are still unimplemented(...) placeholders: silent and dark. All are written;
# a new pad mode can start here, with placeholders in its bindings layer.
NOT_WRITTEN = ()

# The FL window each pad mode brings forward when the encoder turns to it, as the window buttons do.
WINDOWS = {CHANNELS: midi.widChannelRack, MIXER: midi.widMixer}


def show(state):
    """Show the current pad mode in FL's hint bar."""
    suffix = " (not written yet)" if state.pad_mode in NOT_WRITTEN else ""
    ui.setHintMsg("Pad mode: %s%s" % (NAMES[state.pad_mode], suffix))


def step(state, delta):
    """The Pad Mode override's turn: the next or previous pad mode, one per encoder message,
    stopping at Channels and Mixer. Turning to Channels or Mixer shows and focuses its window
    (WINDOWS); turning against an end leaves the focus alone."""
    index = PAD_MODES.index(state.pad_mode) + (1 if delta > 0 else -1)
    pad_mode = PAD_MODES[max(0, min(len(PAD_MODES) - 1, index))]
    if pad_mode != state.pad_mode and pad_mode in WINDOWS:
        ui.showWindow(WINDOWS[pad_mode])
        ui.setFocused(WINDOWS[pad_mode])
    state.pad_mode = pad_mode
    show(state)
