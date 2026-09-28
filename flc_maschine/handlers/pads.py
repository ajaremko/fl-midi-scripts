"""
Pads: play notes on the selected channel, translated to the selected pad group's notes.

While the selected channel is FPC, Groups E and F play FPC's two banks instead (see notes.py)
and the other groups are silent.
"""

from .. import events, fpc, log, notes
from .common import on_press

# Velocity pads play at while fixed velocity (Pad Mode) is on.
FIXED_VELOCITY = 127

# The group that plays FPC's bank A, which the pads jump to when an FPC is selected.
FPC_START_GROUP = next(group for group, bank in notes.FPC_BANK_FOR_GROUP.items() if bank == 0)


def _note_for_press(state, fl, pad_index):
    """The note a pad plays now, or None if it should be silent.

    Uses the last render's snapshot (fl) rather than querying FL: this runs in OnMidiMsg, which FL
    can call at the same time as other callbacks.
    """
    if fl.fpc_channel is None or fl.fpc_banks is None:
        return notes.pad_note(state.pad_group, pad_index)

    bank = notes.FPC_BANK_FOR_GROUP.get(state.pad_group)
    if bank is None:
        return None
    pad = fl.fpc_banks[bank][pad_index]
    return None if pad.empty else pad.note


def play(controller, ev):
    """Rewrite the pad's note and hand the message to FL Studio, which plays it."""
    state = controller.state
    pad_id = ev.control.id

    if ev.is_press:
        note = _note_for_press(state, controller.fl, notes.PAD_INDEX[pad_id])
        if note is not None:
            state.sounding[pad_id] = note
    elif ev.is_release:
        note = state.sounding.pop(pad_id, None)
    elif ev.kind == events.PRESSURE:
        note = state.sounding.get(pad_id)
    else:
        return

    # No note means a silent pad, or a release or aftertouch without a press we played; drop it.
    if note is None:
        return
    ev.raw.data1 = note
    if ev.is_press and state.fixed_velocity:
        ev.raw.data2 = FIXED_VELOCITY
    ev.pass_to_fl()


@on_press
def toggle_fixed_velocity(controller, ev):
    """Pad Mode: turn fixed (full) pad velocity on or off."""
    controller.state.fixed_velocity = not controller.state.fixed_velocity


def follow_fpc_selection(state, fl):
    """Jump to the bank A group (Group E) when an FPC channel becomes selected."""
    if fl.fpc_channel is not None and fl.fpc_channel != state.fpc_channel:
        state.pad_group = FPC_START_GROUP
        if log.DEBUG_FPC_COLORS:
            fpc.log_colour_sources(fl.fpc_channel)
    state.fpc_channel = fl.fpc_channel
