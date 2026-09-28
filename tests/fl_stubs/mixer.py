"""Stand-in for FL Studio's mixer module."""

import transport


def getSongTickPos(mode=-1):
    # FL reports the playhead here in absolute ticks; follow the transport stub's position.
    return transport.song_pos
