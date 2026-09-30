"""
Tells the MK2 bridge (mk2_bridge/bridge.py) what Note Repeat needs: whether it is on, the repeat
rate and the tempo. Used only by the Bridge entry script. The bridge does the timing; this sends
state, from OnIdle like the LEDs, and only what changed since the last send.

The messages are control changes on MIDI channel 16, which the MK2 template never uses, so the
bridge can take them out of the LED stream (it doesn't pass channel 16 on to the MK2):

    CC 1              note repeat: 0 off, 127 on
    CC 2, then CC 34  rate in MIDI clocks (24 per beat), MSB then LSB; the bridge applies it on the LSB.
                      Note Repeat's own rate (handlers/note_repeat.RATES), not FL's snap. Triplets
                      are just other clock counts, so the bridge doesn't know about modes.
    CC 3, then CC 35  tempo x 10 (1200 = 120.0 BPM), MSB then LSB; used while FL is stopped
    CC 4              FL playing: 0 stopped, 127 playing (so the bridge can tell when the clock is missing)
    CC 5              pads play notes: 127 with no mode on, 0 in Shift, New or Color mode, where pads
                      are functions that the bridge mustn't hold back or repeat
    CC 126 (bridge -> script)  FL is playing but no MIDI clock arrives: Send master sync is off
    CC 127 (bridge -> script)  hello: the bridge (re)started, so everything is sent again

Keep these numbers in step with mk2_bridge/bridge.py.
"""

import device
import midi

from . import bindings
from .handlers import note_repeat

CHANNEL = 15  # MIDI channel 16
CC_REPEAT = 1
CC_RATE, CC_RATE_LSB = 2, 34
CC_TEMPO, CC_TEMPO_LSB = 3, 35
CC_PLAYING = 4
CC_PADS_PLAY_NOTES = 5
CC_NO_CLOCK = 126  # bridge -> script
CC_HELLO = 127  # bridge -> script
FROM_BRIDGE = (CC_NO_CLOCK, CC_HELLO)

MAX_14BIT = 0x3FFF

NO_CLOCK_WARNING = ("Note Repeat isn't locked to the song: tick Send master sync on MK2 Bridge Out "
                    "in FL's MIDI settings.")


def _from_bridge(event, control):
    return (event.midiId == midi.MIDI_CONTROLCHANGE and event.midiChan == CHANNEL
            and event.data1 == control)


def is_hello(event):
    """The bridge's hello, as FL delivers it to OnMidiMsg."""
    return _from_bridge(event, CC_HELLO)


def is_no_clock(event):
    """The bridge's warning that FL is playing without sending it a MIDI clock."""
    return _from_bridge(event, CC_NO_CLOCK)


class BridgeLink:
    def __init__(self):
        self._sent = {}  # "repeat" / "rate" / "tempo" -> the value last sent

    def _cc(self, control, value):
        device.midiOutMsg(midi.MIDI_CONTROLCHANGE + CHANNEL + (control << 8) + (value << 16))

    def invalidate(self):
        """Forget what was sent, so the next write sends everything (on init, and on the bridge's hello)."""
        self._sent.clear()

    def write(self, state, fl):
        if not device.isAssigned():
            return
        self._send_7bit("repeat", CC_REPEAT, 127 if state.note_repeat else 0)
        self._send_14bit("rate", CC_RATE, CC_RATE_LSB, note_repeat.rate_clocks(state))
        self._send_14bit("tempo", CC_TEMPO, CC_TEMPO_LSB, max(0, min(MAX_14BIT, int(round(fl.tempo * 10)))))
        self._send_7bit("playing", CC_PLAYING, 127 if fl.playing else 0)
        self._send_7bit("pads", CC_PADS_PLAY_NOTES, 127 if bindings.pads_play_notes(state) else 0)

    def _send_7bit(self, key, control, value):
        if self._sent.get(key) != value:
            self._cc(control, value)
            self._sent[key] = value

    def _send_14bit(self, key, msb_control, lsb_control, value):
        if self._sent.get(key) != value:
            self._cc(msb_control, value >> 7)
            self._cc(lsb_control, value & 0x7F)  # last: the bridge applies the value on the LSB
            self._sent[key] = value
