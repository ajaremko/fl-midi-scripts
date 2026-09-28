"""Stand-in for FL Studio's ui module. Only one window is focused at a time."""

focused = None
snap_mode = 3  # Snap_None


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
