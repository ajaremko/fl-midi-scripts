"""Stand-in for FL Studio's channels module."""

selected = -1  # -1: no channel selected
colors = {}  # channel index -> 0xRRGGBB


def selectedChannel(canBeNone=0, offset=0, indexGlobal=0):
    if selected < 0 and not canBeNone:
        return 0
    return selected


def getChannelColor(index):
    return colors.get(index, 0)
