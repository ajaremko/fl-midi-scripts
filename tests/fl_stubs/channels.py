"""Stand-in for FL Studio's channels module."""

selected = -1  # -1: no channel selected
colors = {}  # channel index -> 0xRRGGBB
focused_editors = []  # channel indexes passed to focusEditor
quantized = []  # (index, startOnly) passed to quickQuantize


def selectedChannel(canBeNone=0, offset=0, indexGlobal=0):
    if selected < 0 and not canBeNone:
        return 0
    return selected


def getChannelColor(index):
    return colors.get(index, 0)


def focusEditor(index, useGlobalIndex=False):
    focused_editors.append(index)


def quickQuantize(index, startOnly=1, useGlobalIndex=False):
    quantized.append((index, startOnly))
