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


visible = set()  # windows getVisible reports, besides the focused one
rects = []  # (left, top, width, height, duration, flags) passed to crDisplayRect


def getVisible(window):
    return 1 if window in visible or window == focused else 0


def crDisplayRect(left, top, right, bottom, duration, flags=0):
    rects.append((left, top, right, bottom, duration, flags))

mi_rects = []  # (start, end, duration) passed to miDisplayRect


def miDisplayRect(start, end, duration, flags=0):
    mi_rects.append((start, end, duration))

scrolls = []  # (window, value) passed to scrollWindow


def scrollWindow(index, value, directionFlag=0):
    scrolls.append((index, value))
