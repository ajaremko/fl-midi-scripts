"""
Prefixed logging to FL Studio's Script output window.
"""

PREFIX = "[FLC MK2]"

# Print every incoming MIDI message before it is decoded. Useful when checking the template.
TRACE_MIDI = False

# Print each FPC pad's colour from both FL calls when an FPC channel is selected (see
# fpc.log_colour_sources). Used to re-check the bank B colour issue in known-issues.md.
DEBUG_FPC_COLORS = False


def info(*args):
    print(PREFIX, *args)


def trace_midi(event):
    if TRACE_MIDI:
        info("midi", "id", event.midiId, "chan", event.midiChan, "data1", event.data1, "data2", event.data2)
