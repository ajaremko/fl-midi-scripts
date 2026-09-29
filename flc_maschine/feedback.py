"""
Feedback guard: notices when the script's own output comes back in as input, and stops it.

That happens when FL's MIDI settings route the script's output back into an FL input. With the MK2
bridge it's an easy mistake, because every loopMIDI port shows up in both FL's Input and Output
lists (e.g. MK2 Bridge Out enabled as an input, or MK2 Bridge In given the script's port number in
Outputs). The echoes look like MK2 input: an LED message is the button's own CC, so an echoed Scene
LED is a Scene press, which toggles song mode, which changes the LED, which is sent again... and
the VOLUME button's CC 7 is MIDI channel volume. Left alone it runs away.

Signs of an echo:
- Any note, aftertouch or CC on MIDI channel 2 or 3. Only the script's HSB colour messages use
  them; the MK2 template sends nothing there.
- In bridge mode, any channel-16 message other than the bridge's own (hello, no-clock warning):
  the rest are the script's own bridge_link messages.
- Messages identical to a mono (single-colour button) LED message the script sent moments before,
  arriving often: ECHO_LIMIT of them within ECHO_PERIOD. A single match can be a real press; a loop
  produces dozens a second. This catches loops on channel 1 alone, such as Scene or Play toggling.
  Pads and Groups don't need it: an echoed press makes the script resend all three HSB components,
  and those on channels 2 and 3 trip the guard at once. (Pad releases are note-on velocity 0, the
  same as a hue-0 LED message, so counting pads here would trip on fast real playing.)

Never counted: channel-mode messages (CC 120-127: All Sound Off, Reset Controllers, All Notes Off,
Omni/Mono/Poly). The script never sends them, but FL does, on every channel, after a MIDI input
overflow or a panic; the copy on channel 2 would otherwise look like an echo.

Once tripped, the controller swallows all input and sends nothing until the script is reloaded, so
a setting that's still wrong can't restart the loop.
"""

import time

import midi

from .events import MIDI_KEYAFTERTOUCH

clock = time.time  # replaced in tests

ECHO_WINDOW = 0.25  # seconds: a message matching one sent this recently looks like an echo
ECHO_LIMIT = 8  # this many look-alike echoes within ECHO_PERIOD trips the guard
ECHO_PERIOD = 1.0
FOREIGN_CHANNELS = (1, 2)  # MIDI channels 2 and 3: HSB colour components, never MK2 input
BRIDGE_CHANNEL = 15  # MIDI channel 16: the script's messages to the bridge
FIRST_CHANNEL_MODE_CC = 120  # CC 120-127 are channel-mode messages (see is_channel_mode)
FROM_BRIDGE = (126, 127)  # channel-16 CCs the bridge sends the script (bridge_link.FROM_BRIDGE)

WARNING = ("MK2: FL is receiving its own output, so the script has stopped. In MIDI settings, disable "
           "MK2 Bridge Out in Inputs and clear the port number of MK2 Bridge In in Outputs, then reload "
           "the script.")

_CHANNEL_MESSAGES = (midi.MIDI_NOTEON, midi.MIDI_NOTEOFF, MIDI_KEYAFTERTOUCH, midi.MIDI_CONTROLCHANGE)


def is_channel_mode(event):
    """A channel-mode message (CC 120-127), such as FL's All Notes Off on every channel."""
    return event.midiId == midi.MIDI_CONTROLCHANGE and event.data1 >= FIRST_CHANNEL_MODE_CC


def describe(event):
    """A short description of an incoming message, for the trip warning."""
    kind = {midi.MIDI_NOTEON: "note-on", midi.MIDI_NOTEOFF: "note-off", MIDI_KEYAFTERTOUCH: "aftertouch",
            midi.MIDI_CONTROLCHANGE: "CC"}.get(event.midiId, "message %d" % event.midiId)
    return "channel %d %s %d = %d" % (event.midiChan + 1, kind, event.data1, event.data2)


def _key(midi_id, channel, data1, data2):
    # FL may deliver a note-on with velocity 0 as a note-off; compare them as the same message.
    if midi_id == midi.MIDI_NOTEOFF:
        midi_id, data2 = midi.MIDI_NOTEON, 0
    return midi_id, channel, data1, data2


class FeedbackGuard:
    def __init__(self, bridge=False):
        self.bridge = bridge
        self.tripped = False
        self._sent = {}  # message key -> time last sent
        self._echoes = []  # times of recent look-alike echoes

    def sent(self, message):
        """Record a mono LED message the script sent (a device.midiOutMsg integer)."""
        status = message & 0xFF
        self._sent[_key(status & 0xF0, status & 0x0F, (message >> 8) & 0xFF, message >> 16)] = clock()

    def check(self, event):
        """Whether an incoming event is the script's own output coming back. Trips the guard on a
        sure sign, or when look-alike echoes pile up; after that every event counts."""
        if self.tripped:
            return True
        midi_id, channel = event.midiId, event.midiChan
        if midi_id not in _CHANNEL_MESSAGES or is_channel_mode(event):
            return False
        from_bridge = midi_id == midi.MIDI_CONTROLCHANGE and event.data1 in FROM_BRIDGE
        if channel in FOREIGN_CHANNELS or (self.bridge and channel == BRIDGE_CHANNEL and not from_bridge):
            self.tripped = True
            return True
        now = clock()
        sent_at = self._sent.get(_key(midi_id, channel, event.data1, event.data2))
        if sent_at is not None and now - sent_at <= ECHO_WINDOW:
            self._echoes = [t for t in self._echoes if now - t <= ECHO_PERIOD]
            self._echoes.append(now)
            if len(self._echoes) >= ECHO_LIMIT:
                self.tripped = True
                return True
        return False
