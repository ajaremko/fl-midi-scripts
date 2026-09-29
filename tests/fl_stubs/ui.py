"""Stand-in for FL Studio's ui module. Only one window is focused at a time."""

focused = None
snap_mode = 3  # Snap_None
in_popup_menu = False
hints = []  # messages passed to setHintMsg
event_editors = []  # (eventId, mode) passed to openEventEditor


def getFocused(window):
    return 1 if window == focused else 0


def showWindow(window):
    pass


def setFocused(window):
    global focused
    focused = window


def hideWindow(window):
    global focused
    if focused == window:
        focused = None


def getSnapMode():
    return snap_mode


def isInPopupMenu():
    return 1 if in_popup_menu else 0


def setHintMsg(message):
    hints.append(message)


def openEventEditor(eventId, mode, newWindow=0):
    event_editors.append((eventId, mode))
