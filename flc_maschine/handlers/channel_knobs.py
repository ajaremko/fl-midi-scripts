"""
E1-E8: the selected Channel Rack channel's own settings, the ones every channel has. The knobs are
relative, and the template labels them on the MK2's display (Volume, Pan, Pitch, Range, Gate,
Shift, Swing, Mixer); FL's hint bar shows the parameter and its new value.

Each is a channel REC event: channels.getRecEventId(channel) + a REC_Chan_ offset. A turn steps it
with channels.incEventValue, which works in the event's own units and range, and writes it back
with general.processRECEvent, as Mikey_Maschine does for swing. E4 sets the pitch knob's range
(channels.setChannelPitch, unit 2), and E8 steps the mixer track routing one track at a time, as
the Fire does.
"""

import channels
import general
import midi
import mixer
import ui

from .. import events
from .pads import MAX_PITCH_RANGE

# Knob -> (REC_Chan_ offset, resolution scale). Scale 1.0 is FL's own knob resolution (EKRes) per
# encoder step; raise it for coarser steps, lower it for finer ones.
KNOBS = {
    "E1": (midi.REC_Chan_Vol, 1.0),  # Volume
    "E2": (midi.REC_Chan_Pan, 1.0),  # Pan
    "E3": (midi.REC_Chan_Pitch, 1.0),  # Pitch
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


def turn(controller, ev):
    """E1-E7: step the selected channel's parameter by the turn."""
    if ev.kind != events.TURN:
        return
    channel = _selected_channel()
    if channel < 0:
        return
    offset, scale = KNOBS[ev.control.id]
    event_id = channels.getRecEventId(channel) + offset
    value = channels.incEventValue(event_id, ev.delta, midi.EKRes * scale)
    general.processRECEvent(event_id, value, SET_FLAGS)


def pitch_range(controller, ev):
    """E4: widen or narrow the selected channel's pitch range (the reach of E3's pitch knob), one
    semitone per encoder message, between 1 and MAX_PITCH_RANGE (as for shift Pads 13-16)."""
    if ev.kind != events.TURN:
        return
    channel = _selected_channel()
    if channel < 0:
        return
    current = int(round(channels.getChannelPitch(channel, 2)))
    semitones = max(1, min(MAX_PITCH_RANGE, current + (1 if ev.delta > 0 else -1)))
    if semitones != current:
        channels.setChannelPitch(channel, semitones, 2)  # unit 2: the range
    ui.setHintMsg("Pitch range: +/-%d semitones" % semitones)


def mixer_track(controller, ev):
    """E8: route the selected channel to the next or previous mixer track, one per encoder message."""
    if ev.kind != events.TURN:
        return
    channel = _selected_channel()
    if channel < 0:
        return
    # 0 is Master; trackCount() also counts the "Current" utility track, last, which is left out.
    track = channels.getTargetFxTrack(channel) + (1 if ev.delta > 0 else -1)
    track = max(0, min(mixer.trackCount() - 2, track))
    general.processRECEvent(channels.getRecEventId(channel) + midi.REC_Chan_FXTrack, track,
                            midi.REC_Control | midi.REC_UpdateControl)
    ui.setHintMsg("Mixer track: %d %s" % (track, mixer.getTrackName(track)))
