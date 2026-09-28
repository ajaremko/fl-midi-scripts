"""Stand-in for FL Studio's transport module. Records the calls the script makes."""

playing = False
recording = False
song_pos = 0  # absolute ticks
calls = []


def reset():
    global playing, recording, song_pos
    playing = False
    recording = False
    song_pos = 0
    del calls[:]


def isPlaying():
    return 1 if playing else 0


def isRecording():
    return 1 if recording else 0


def start():
    global playing
    calls.append(("start",))
    playing = not playing


def stop():
    global playing
    calls.append(("stop",))
    playing = False


def record():
    global recording
    calls.append(("record",))
    recording = not recording


def setSongPos(pos, mode=-1):
    global song_pos
    calls.append(("setSongPos", pos, mode))
    song_pos = pos


def globalTransport(command, value, pmeflags=0, flags=0):
    calls.append(("globalTransport", command, value))
