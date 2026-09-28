"""Stand-in for FL Studio's general module."""

ppq = 96  # ticks per beat
ppb = 384  # ticks per bar (4/4)
calls = []  # undo calls, in order
safe = True  # what safeToEdit reports


def getRecPPQ():
    return ppq


def getRecPPB():
    return ppb


def undoUp():
    calls.append("undoUp")


def undoDown():
    calls.append("undoDown")


def safeToEdit():
    return 1 if safe else 0


def getVersion():
    return 99
