"""
Turns FL Studio's raw MIDI events into ControlEvents, using each control's template mode to work
out whether a message is a press, a release, a turn and so on.
"""

import midi

from . import controls

PRESS = "press"
RELEASE = "release"
TURN = "turn"  # relative encoder; see ControlEvent.delta
VALUE = "value"  # absolute encoder; see ControlEvent.value
PRESSURE = "pressure"  # pad aftertouch; see ControlEvent.value

# Poly aftertouch status. No shipped script uses FL's name for it, so fall back to the MIDI value.
MIDI_KEYAFTERTOUCH = getattr(midi, "MIDI_KEYAFTERTOUCH", 0xA0)


class ControlEvent:
    __slots__ = ("control", "kind", "value", "delta", "raw")

    def __init__(self, control, kind, value, raw, delta=0):
        self.control = control
        self.kind = kind
        self.value = value
        self.delta = delta
        self.raw = raw

    @property
    def is_press(self):
        return self.kind == PRESS

    @property
    def is_release(self):
        return self.kind == RELEASE

    def pass_to_fl(self):
        """Let FL Studio's own handling (playing notes, linked controls) process the message."""
        self.raw.handled = False

    def __repr__(self):
        return "ControlEvent(%s %s value=%d delta=%d)" % (self.control.id, self.kind, self.value, self.delta)


def _decode_relative(value):
    return value - 128 if value >= 64 else value


def decode(event):
    """Return a ControlEvent for the message, or None if no control sends it."""
    midi_id = event.midiId
    value = event.data2

    if midi_id == midi.MIDI_CONTROLCHANGE:
        control = controls.BY_KEY.get((controls.CC, event.midiChan, event.data1))
    elif midi_id in (midi.MIDI_NOTEON, midi.MIDI_NOTEOFF, MIDI_KEYAFTERTOUCH):
        control = controls.BY_KEY.get((controls.NOTE, event.midiChan, event.data1))
    else:
        return None

    if control is None:
        return None

    if midi_id == MIDI_KEYAFTERTOUCH:
        return ControlEvent(control, PRESSURE, value, event)
    if midi_id == midi.MIDI_NOTEOFF:
        return ControlEvent(control, RELEASE, 0, event)

    mode = control.mode
    if mode == controls.COMP:
        return ControlEvent(control, TURN, value, event, _decode_relative(value))
    if mode == controls.ABSOLUTE:
        return ControlEvent(control, VALUE, value, event)
    if mode == controls.GATE:
        return ControlEvent(control, PRESS if value > 0 else RELEASE, value, event)
    # TRIGGER sends only on press. TOGGLE sends 127 and 0 on alternate presses, and each one is a press.
    return ControlEvent(control, PRESS, value, event)
