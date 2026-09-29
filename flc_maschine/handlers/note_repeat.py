"""
Note Repeat (bridge entry script only). The MK2 bridge does the repeating; bridge_link.py tells it
the mode, rate and tempo.

The button cycles three modes: Off -> On (straight divisions) -> Triplets (triplet divisions) -> Off.
Each mode has its own rates, so the encoder never mixes straight and triplet grids. One division
index is shared, so switching modes keeps the division (1/16 <-> 1/16T). The rate belongs to Note
Repeat, not to FL's grid snap: while Note Repeat is on, turning the master encoder steps through
the mode's rates (encoder.turn calls step_rate), and the hint bar shows the mode and rate.
"""

import ui

from .common import on_press

OFF, ON, TRIPLETS = 0, 1, 2  # OFF is falsy: `if state.note_repeat` means "on in either mode"

# Per mode, slow to fast: (name, MIDI clocks per repeat at 24 per beat). Every one divides a 4/4
# bar (96 clocks), so all the grids line up with the bar.
RATES = {
    ON: [("1/4", 24), ("1/8", 12), ("1/16", 6), ("1/32", 3)],
    TRIPLETS: [("1/4T", 16), ("1/8T", 8), ("1/16T", 4), ("1/32T", 2)],
}
DEFAULT_RATE = 2  # 1/16 or 1/16T


def _rate(state):
    # While Off, the straight list still gives the bridge a sensible rate.
    return RATES.get(state.note_repeat, RATES[ON])[state.note_repeat_rate]


def rate_name(state):
    return _rate(state)[0]


def rate_clocks(state):
    return _rate(state)[1]


def _hint(state):
    if state.note_repeat == OFF:
        ui.setHintMsg("Note Repeat: off")
    elif state.note_repeat == TRIPLETS:
        ui.setHintMsg("Note Repeat: triplets, %s" % rate_name(state))
    else:
        ui.setHintMsg("Note Repeat: %s" % rate_name(state))


@on_press
def toggle(controller, ev):
    """Note Repeat button: Off -> On -> Triplets -> Off."""
    state = controller.state
    state.note_repeat = {OFF: ON, ON: TRIPLETS, TRIPLETS: OFF}[state.note_repeat]
    _hint(state)


def step_rate(state, delta):
    """An encoder turn while Note Repeat is on: one rate per message within the mode, clockwise faster."""
    index = max(0, min(len(RATES[ON]) - 1, state.note_repeat_rate + (1 if delta > 0 else -1)))
    if index != state.note_repeat_rate:
        state.note_repeat_rate = index
        ui.setHintMsg("Note Repeat: %s" % rate_name(state))
