"""
Sends a rendered frame to the controller's LEDs. This is the only module that sends MIDI to the
controller. It remembers what each LED was last sent and only sends changes.
"""

import device
import midi

from .. import controls
from . import colors

# Channels that carry hue, saturation and brightness for an LED in HSB colour mode.
HSB_CHANNELS = (0, 1, 2)


def _send(control, channel, value):
    status = midi.MIDI_CONTROLCHANGE if control.msg == controls.CC else midi.MIDI_NOTEON
    device.midiOutMsg(status + channel + (control.number << 8) + (value << 16))


class LedWriter:
    def __init__(self):
        self._sent = {}

    def invalidate(self, control_id=None):
        """Forget what was sent, so the next write resends it. None forgets every LED."""
        if control_id is None:
            self._sent.clear()
        else:
            self._sent.pop(control_id, None)

    def write(self, frame):
        if not device.isAssigned():
            return
        for control in controls.LED_CONTROLS:
            if control.led == controls.HSB:
                self._write_hsb(control, frame.get(control.id, colors.OFF))
            else:
                self._write_mono(control, frame.get(control.id, False))

    def _write_mono(self, control, wanted):
        if self._sent.get(control.id) == wanted:
            return
        _send(control, control.channel, 127 if wanted else 0)
        self._sent[control.id] = wanted

    def _write_hsb(self, control, wanted):
        # HSB takes three messages per LED, and NI warns that heavy HSB traffic can stall the
        # controller, so only resend the components that changed.
        sent = self._sent.get(control.id)
        for i, channel in enumerate(HSB_CHANNELS):
            if sent is None or sent[i] != wanted[i]:
                _send(control, channel, wanted[i])
        self._sent[control.id] = wanted
