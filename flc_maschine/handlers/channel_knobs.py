"""
E1-E8: the selected Channel Rack channel's own settings, the ones every channel has. The knobs are
relative, and the template labels them on the MK2's display (Volume, Pan, Mod X, Mod Y, Gate,
Shift, Swing, Mixer); FL's hint bar shows the parameter and its new value.

E1-E7 are channel REC events: channels.getRecEventId(channel) + a REC_Chan_ offset. A turn steps it
with channels.incEventValue, which works in the event's own units and range, and writes it back
with general.processRECEvent, as Mikey_Maschine does for swing. E3 and E4 are the channel's Mod X
and Mod Y, whose events keep their old filter names (REC_Chan_FCut, REC_Chan_FRes); FL decides what
they modulate. E8 steps the mixer track routing one track at a time, as the Fire does.

With several channels selected, the first selected channel steps as usual and the others follow it:
E1-E7 set them to its new value (so they end up equal), and E8 routes them to its new track. Only
the first channel's write shows FL's hint.
"""

import channels
import general
import midi
import mixer
import ui

from .. import events

# Knob -> (REC_Chan_ offset, resolution scale). Scale 1.0 is FL's own knob resolution (EKRes) per
# encoder step; raise it for coarser steps, lower it for finer ones.
KNOBS = {
    "E1": (midi.REC_Chan_Vol, 1.0),  # Volume
    "E2": (midi.REC_Chan_Pan, 1.0),  # Pan
    "E3": (midi.REC_Chan_FCut, 1.0),  # Mod X
    "E4": (midi.REC_Chan_FRes, 1.0),  # Mod Y
    "E5": (midi.REC_Chan_GateTime, 1.0),  # Gate
    "E6": (midi.REC_Chan_TimeOfs, 1.0),  # Shift: time offset
    "E7": (midi.REC_Chan_SwingMix, 1.0),  # Swing
}

# Write the value, move FL's own knob, and show the parameter and value in the hint bar.
SET_FLAGS = midi.REC_UpdateValue | midi.REC_UpdateControl | midi.REC_ShowHint


def _selected_channel():
    channel = channels.selectedChannel(1)  # -1 when no channel is selected
    if channel < 0:
        ui.setHintMsg("No channel selected")
    return channel


def _other_selected(primary):
    """The selected channels besides the first (primary) one."""
    return [channel for channel in range(channels.channelCount())
            if channel != primary and channels.isChannelSelected(channel)]


# The other selected channels' writes: the value and FL's control, but no hint (the first channel's
# hint stays up rather than flickering through every channel).
FOLLOW_FLAGS = midi.REC_UpdateValue | midi.REC_UpdateControl


def turn(controller, ev):
    """E1-E7: step the selected channel's parameter by the turn, and set the other selected channels
    to its new value."""
    if ev.kind != events.TURN:
        return
    channel = _selected_channel()
    if channel < 0:
        return
    offset, scale = KNOBS[ev.control.id]
    event_id = channels.getRecEventId(channel) + offset
    value = channels.incEventValue(event_id, ev.delta, midi.EKRes * scale)
    general.processRECEvent(event_id, value, SET_FLAGS)
    for other in _other_selected(channel):
        general.processRECEvent(channels.getRecEventId(other) + offset, value, FOLLOW_FLAGS)
    controller.state.last_event_id = event_id  # for Shift + Sampling (Edit)


def mixer_track(controller, ev):
    """E8: route the selected channel to the next or previous mixer track, one per encoder message,
    and the other selected channels to the same track."""
    if ev.kind != events.TURN:
        return
    channel = _selected_channel()
    if channel < 0:
        return
    # 0 is Master; trackCount() also counts the "Current" utility track, last, which is left out.
    track = channels.getTargetFxTrack(channel) + (1 if ev.delta > 0 else -1)
    track = max(0, min(mixer.trackCount() - 2, track))
    routed = [channel] + _other_selected(channel)
    for each in routed:
        general.processRECEvent(channels.getRecEventId(each) + midi.REC_Chan_FXTrack, track,
                                midi.REC_Control | midi.REC_UpdateControl)
    count = " (%d channels)" % len(routed) if len(routed) > 1 else ""
    ui.setHintMsg("Mixer track: %d %s%s" % (track, mixer.getTrackName(track), count))
