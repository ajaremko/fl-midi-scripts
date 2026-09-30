"""Stand-in for FL Studio's general module."""

ppq = 96  # ticks per beat
ppb = 384  # ticks per bar (4/4)
calls = []  # undo calls, in order
rec_events = []  # (eventId, value, flags) passed to processRECEvent, except reads
rec_values = {}  # eventId -> value
safe = True  # what safeToEdit reports


def getRecPPQ():
    return ppq


def getRecPPB():
    return ppb


def undo():
    calls.append("undo")


def undoUp():
    calls.append("undoUp")


def undoDown():
    calls.append("undoDown")


def safeToEdit():
    return 1 if safe else 0


def getVersion():
    return 99


def processRECEvent(eventId, value, flags):
    if flags & 2:  # REC_GetValue
        return rec_values.get(eventId, 0)
    rec_events.append((eventId, value, flags))
    rec_values[eventId] = value
    return value


undo_points = []  # (name, flags) passed to saveUndo


def saveUndo(undoName, flags, updateHistory=1):
    undo_points.append((undoName, flags))
