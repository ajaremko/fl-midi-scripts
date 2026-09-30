"""
F16: route the selected channel(s) to empty mixer tracks, like FL's "Assign selected to free mixer
track(s)" (Ctrl+L in the Channel Rack), which scripts can't call directly.

Each selected channel, in order, gets the next empty insert track, which then takes the channel's
name and colour. A channel already on a track of its own is moved on too, as FL does; its old track
keeps the channel's name, so it isn't picked again.

An empty track has no channel routed to it (in any channel group), no effect plugin in any slot,
and still its default name. The last two keep buses (a reverb fed by sends has no channels) and
tracks set up by hand from being taken. A track fed only by sends from other tracks, with no
effects and its default name, still counts as empty: checking every route would take thousands of
calls.
"""

import channels
import general
import midi
import mixer
import ui

from .common import on_press

EFFECT_SLOTS = 10  # a mixer track's effect slots


def is_default_name(track):
    # FL shows an unnamed track as "Insert N"; an empty name is accepted too, in case the API
    # returns that for one.
    return mixer.getTrackName(track) in ("", "Insert %d" % track)


def used_tracks():
    """Master and every mixer track in use, lowest first: routed to from a channel (in any channel
    group) or given a name. Mixer mode's Group buttons jump by blocks of these. Tracks with only
    effects don't count: checking every slot of every track would cost ~1,300 FL calls a redraw."""
    used = {0} | {channels.getTargetFxTrack(i, True) for i in range(channels.channelCount(1))}
    used |= {track for track in range(1, mixer.trackCount() - 1) if not is_default_name(track)}
    return sorted(track for track in used if 0 <= track < mixer.trackCount() - 1)


def empty_tracks():
    """Insert tracks with no channel routed to them, no effects and their default name, lowest
    first. 0 is Master, and trackCount()'s last track is the "Current" utility track."""
    used = {channels.getTargetFxTrack(i, True) for i in range(channels.channelCount(1))}
    return [track for track in range(1, mixer.trackCount() - 1)
            if track not in used
            and not any(mixer.isTrackPluginValid(track, slot) for slot in range(EFFECT_SLOTS))
            and is_default_name(track)]


@on_press
def assign_free_track(controller, ev):
    selected = [c for c in range(channels.channelCount()) if channels.isChannelSelected(c)]
    if not selected:
        ui.setHintMsg("No channel selected")
        return
    free = empty_tracks()
    assigned = []
    for channel, track in zip(selected, free):
        general.processRECEvent(channels.getRecEventId(channel) + midi.REC_Chan_FXTrack, track,
                                midi.REC_Control | midi.REC_UpdateControl)
        mixer.setTrackColor(track, channels.getChannelColor(channel))
        mixer.setTrackName(track, channels.getChannelName(channel))
        assigned.append(track)
    if not assigned:
        ui.setHintMsg("No empty mixer track")
        return
    mixer.setTrackNumber(assigned[0], midi.curfxScrollToMakeVisible)
    if len(assigned) < len(selected):
        ui.setHintMsg("No empty mixer track for %d of %d channels" % (len(selected) - len(assigned), len(selected)))
    elif len(assigned) == 1:
        ui.setHintMsg("Mixer track %d: %s" % (assigned[0], channels.getChannelName(selected[0])))
    else:
        ui.setHintMsg("Mixer tracks %s" % ", ".join(str(track) for track in assigned))
