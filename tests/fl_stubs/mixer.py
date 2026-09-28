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
