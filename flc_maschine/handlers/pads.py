"""
Pads: play notes on the selected channel, translated to the selected pad group's notes.

While the selected channel is FPC, Groups E and F play FPC's two banks instead (see notes.py)
and the other groups are silent.
"""

import channels
import ui

from .. import events, fpc, log, notes
from .common import on_press

# Velocity pads play at while fixed velocity (Pad Mode) is on.
FIXED_VELOCITY = 127

# Shift pads 13-16 change the selected channel's pitch. When a step goes past the channel's pitch
# range, the range is widened to the first of these (in semitones) that covers it; the pitch
# stops at MAX_PITCH_RANGE either way.
PITCH_RANGE_STEPS = (12, 24, 36, 48)
MAX_PITCH_RANGE = PITCH_RANGE_STEPS[-1]

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


def transpose(semitones):
    """Shift pads 13-16: move the selected channel's pitch by `semitones`, so FL shows it on the
    channel's pitch knob. Widens the channel's pitch range when the new pitch is outside it.

    Works in semitones from the normalised pitch (mode 0) and the range (mode 2) rather than the
    API's semitone mode, which the manual and vendor scripts disagree on (semitones or cents).
    """

    @on_press
    def handler(controller, ev):
        channel = channels.selectedChannel(1)
        if channel < 0:
            return
        pitch_range = channels.getChannelPitch(channel, 2)
        current = round(channels.getChannelPitch(channel, 0) * pitch_range)
        target = max(-MAX_PITCH_RANGE, min(MAX_PITCH_RANGE, current + semitones))
        if abs(target) > pitch_range:
            pitch_range = next(step for step in PITCH_RANGE_STEPS if step >= abs(target))
            channels.setChannelPitch(channel, pitch_range, 2)
        channels.setChannelPitch(channel, target / pitch_range, 0)
        ui.setHintMsg("Channel pitch: %+d semitones (range +/-%d)" % (target, pitch_range))

    return handler


def follow_fpc_selection(state, fl):
    """Jump to the bank A group (Group E) when an FPC channel becomes selected."""
    if fl.fpc_channel is not None and fl.fpc_channel != state.fpc_channel:
        state.pad_group = FPC_START_GROUP
        if log.DEBUG_FPC_COLORS:
            fpc.log_colour_sources(fl.fpc_channel)
    state.fpc_channel = fl.fpc_channel
