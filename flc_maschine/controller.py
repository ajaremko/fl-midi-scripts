import device

from . import dispatcher, events, log
from .handlers import pads
from .rendering import renderer
from .rendering.fl_state import FlSnapshot
from .rendering.output import LedWriter
from .state import ControllerState


class MaschineMk2:
    def __init__(self):
        self.state = ControllerState()
        self.leds = LedWriter()

    def on_init(self):
        log.info("init on port", device.getPortNumber() if device.isAssigned() else "(no output port)")
        self.leds.invalidate()
        self.render()

    def on_deinit(self):
        log.info("deinit")
        self.leds.write({})

    def on_midi_msg(self, event):
        log.trace_midi(event)
        ev = events.decode(event)
        if ev is None:
            log.info("unmapped midi", "id", event.midiId, "chan", event.midiChan, "data1", event.data1, "data2", event.data2)
            return
        if ev.is_press or ev.is_release:
            # Buttons with LED "For MIDI Out" in the template light themselves when pressed,
            # so resend whatever the renderer wants for this control.
            self.leds.invalidate(ev.control.id)
        dispatcher.dispatch(self, ev)
        self.render()

    def on_refresh(self, flags):
        self.render()

    def on_idle(self):
        return

    def render(self):
        fl = FlSnapshot.read()
        pads.follow_fpc_selection(self.state, fl)
        self.leds.write(renderer.render(self.state, fl))
