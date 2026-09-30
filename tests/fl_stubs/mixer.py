"""Stand-in for FL Studio's mixer module."""

import transport


def getSongTickPos(mode=-1):
    # FL reports the playhead here in absolute ticks; follow the transport stub's position.
    return transport.song_pos


track_volume = {0: 0.8}  # track index -> volume, 0-1


def getTrackVolume(index, mode=0):
    return track_volume[index]


def setTrackVolume(index, volume, pickupMode=0):
    track_volume[index] = volume


track_number = 0  # trackNumber(): the current track
track_count = 10  # trackCount(): Master, inserts 1-8 and the "Current" utility track
selected_tracks = set()


def trackNumber():
    return track_number


def trackCount():
    return track_count


def setActiveTrack(index):
    global track_number
    track_number = index
    selected_tracks.clear()
    selected_tracks.add(index)


def selectTrack(index):
    if index in selected_tracks:
        selected_tracks.discard(index)
    else:
        selected_tracks.add(index)


def isTrackSelected(index):
    return 1 if index in selected_tracks else 0


tempo = 120.0  # getCurrentTempo, in BPM


def getCurrentTempo(asInt=0):
    return tempo


def getTrackName(index):
    return "Master" if index == 0 else "Insert %d" % index


active_effect = None  # (track, slot) of the focused effect editor, or None


def getActiveEffectIndex():
    return active_effect
