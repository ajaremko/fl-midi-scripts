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


track_names = {}  # track index -> name set by setTrackName (default "Master" / "Insert N")
track_colors = {}  # track index -> colour set by setTrackColor
track_effects = set()  # (track, slot) with a valid effect plugin
track_number_flags = []  # (index, flags) passed to setTrackNumber


def getTrackName(index, maxLen=-1):
    return track_names.get(index, "Master" if index == 0 else "Insert %d" % index)


def setTrackName(index, name):
    track_names[index] = name


def setTrackColor(index, color):
    track_colors[index] = color


def isTrackPluginValid(index, plugIndex):
    return 1 if (index, plugIndex) in track_effects else 0


def setTrackNumber(index, flags=-1):
    global track_number
    track_number = index
    track_number_flags.append((index, flags))


active_effect = None  # (track, slot) of the focused effect editor, or None


def getActiveEffectIndex():
    return active_effect


step_pos = -1  # getSongStepPos(): the step FL is playing, -1 when stopped


def getSongStepPos():
    return step_pos
