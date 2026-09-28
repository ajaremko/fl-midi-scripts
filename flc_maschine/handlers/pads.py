"""
Pads: play notes on the selected channel, translated to the selected pad group's notes.

While the selected channel is FPC, Groups E and F play FPC's two banks instead (see notes.py)
and the other groups are silent.
"""

from .. import events, fpc, log, notes

# The group that plays FPC's bank A, which the pads jump to when an FPC is selected.
FPC_START_GROUP = next(group for group, bank in notes.FPC_BANK_FOR_GROUP.items() if bank == 0)


def _note_for_press(state, pad_index):
    """The note a pad plays now, or None if it should be silent."""
    channel = fpc.selected_fpc_channel()
    if channel is None:
        return notes.pad_note(state.pad_group, pad_index)

    bank = notes.FPC_BANK_FOR_GROUP.get(state.pad_group)
    if bank is None:
        return None
    pad = fpc.read_pad(channel, notes.fpc_pad(bank, pad_index))
    return None if pad.empty else pad.note


def play(controller, ev):
    """Rewrite the pad's note and hand the message to FL Studio, which plays it."""
    state = controller.state
    pad_id = ev.control.id

    if ev.is_press:
        note = _note_for_press(state, notes.PAD_INDEX[pad_id])
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
    ev.pass_to_fl()


def follow_fpc_selection(state, fl):
    """Jump to the bank A group (Group E) when an FPC channel becomes selected."""
    if fl.fpc_channel is not None and fl.fpc_channel != state.fpc_channel:
        state.pad_group = FPC_START_GROUP
        if log.DEBUG_FPC_COLORS:
            fpc.log_colour_sources(fl.fpc_channel)
    state.fpc_channel = fl.fpc_channel
