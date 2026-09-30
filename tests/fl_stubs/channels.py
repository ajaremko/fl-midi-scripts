"""Stand-in for FL Studio's channels module."""

selected = -1  # -1: no channel selected
colors = {}  # channel index -> 0xRRGGBB
shown_forms = []  # (index, state) passed to showCSForm
quantized = []  # (index, startOnly) passed to quickQuantize
pitch = {}  # channel index -> normalised pitch, -1..1 of its range (default 0)
pitch_range = {}  # channel index -> pitch range in semitones (default 2, FL's default)
pitch_calls = []  # (index, value, pitchUnit) passed to setChannelPitch
muted = set()  # muted channel indexes
soloed = None  # the soloed channel index, or None
count = 8  # channelCount(): the current group's channels, global indexes 0 to count - 1
global_count = None  # channelCount(1), when other groups add channels after them; None: count
names = {}  # channel index -> name (default "Channel N")
selection = set()  # channel indexes selected by select/selectOneChannel (separate from `selected`)


def selectedChannel(canBeNone=0, offset=0, indexGlobal=0):
    if selected < 0 and not canBeNone:
        return 0
    return selected


def getChannelColor(index, useGlobalIndex=False):
    return colors.get(index, 0)


def quickQuantize(index, startOnly=1, useGlobalIndex=False):
    quantized.append((index, startOnly))


def getChannelPitch(index, mode=0, useGlobalIndex=False):
    if mode == 0:
        return pitch.get(index, 0.0)
    if mode == 2:
        return pitch_range.get(index, 2)
    raise NotImplementedError("the script doesn't use pitch mode %r" % mode)


def setChannelPitch(index, value, pitchUnit=0, pickupMode=0, useGlobalIndex=False):
    pitch_calls.append((index, value, pitchUnit))
    if pitchUnit == 0:
        pitch[index] = max(-1.0, min(1.0, value))
    elif pitchUnit == 2:
        pitch_range[index] = value
    else:
        raise NotImplementedError("the script doesn't use pitch unit %r" % pitchUnit)


def muteChannel(index, value=-1, useGlobalIndex=False):
    if index in muted:
        muted.discard(index)
    else:
        muted.add(index)


def isChannelMuted(index, useGlobalIndex=False):
    return 1 if index in muted else 0


def soloChannel(index, useGlobalIndex=False):
    global soloed
    soloed = None if soloed == index else index


def isChannelSolo(index, useGlobalIndex=False):
    return 1 if soloed == index else 0


def channelCount(globalCount=0):
    return global_count if globalCount and global_count is not None else count


def getChannelName(index, useGlobalIndex=False):
    return names.get(index, "Channel %d" % (index + 1))


def selectOneChannel(index, useGlobalIndex=False):
    selection.clear()
    selection.add(index)


def selectChannel(index, value=-1, useGlobalIndex=False):
    if value == 1 or (value == -1 and index not in selection):
        selection.add(index)
    else:
        selection.discard(index)


def isChannelSelected(index, useGlobalIndex=False):
    return 1 if index in selection else 0


def showCSForm(index, state=1, useGlobalIndex=False):
    shown_forms.append((index, state))


def getRecEventId(index, useGlobalIndex=False):
    return (index + 1) << 16  # a distinct base per channel


fx_tracks = {}  # channel index -> mixer track (getTargetFxTrack)
inc_calls = []  # (eventId, step, res) passed to incEventValue


def incEventValue(eventId, step, res=1.0 / 64):
    import general
    inc_calls.append((eventId, step, res))
    return general.rec_values.get(eventId, 0) + step  # the stub steps in whole units


def getTargetFxTrack(index, useGlobalIndex=False):
    import general
    return general.rec_values.get(getRecEventId(index) + 8, fx_tracks.get(index, 0))


types = {}  # channel index -> channel type (default: a generator plugin)


def getChannelType(index, useGlobalIndex=False):
    import midi
    return types.get(index, midi.CT_GenPlug)


def setChannelColor(index, color, useGlobalIndex=False):
    colors[index] = color
