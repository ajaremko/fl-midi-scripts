import device
import general

from . import diagnostics, dispatcher, events, log
from .handlers import pads, ui_commands
from .rendering import renderer
from .rendering.fl_state import FlSnapshot
from .rendering.output import LedWriter
from .state import ControllerState


class MaschineMk2:
    def __init__(self):
        self.state = ControllerState()
        self.leds = LedWriter()
        # FL can run OnMidiMsg and OnRefresh at the same time on different threads, so neither
        # reads FL state or writes LEDs: they set `dirty`, and OnIdle renders. LEDs to resend are
        # collected in `invalidated` for the same reason.
        self.dirty = False
        self.invalidated = set()
        self.unsafe_noted = False
        # The latest FL snapshot, from the last render. Handlers use it instead of querying FL.
        self.fl = FlSnapshot()

    def on_init(self):
        log.info("init on port", device.getPortNumber() if device.isAssigned() else "(no output port)")
        self.leds.invalidate()
        self.dirty = True
        self._render_if_due()

    def on_deinit(self):
        log.info("deinit")
        self.leds.write({})

    def on_midi_msg(self, event):
        log.trace_midi(event)
        ev = events.decode(event)
        if ev is None:
            log.info("unmapped midi", "id", event.midiId, "chan", event.midiChan, "data1", event.data1, "data2", event.data2)
            return
        if ev.kind == events.PRESSURE:
            diagnostics.count("aftertouch")
        else:
            diagnostics.note("midi %s %s %d" % (ev.control.id, ev.kind, ev.value))
        if ev.is_press or ev.is_release:
            # Buttons with LED "For MIDI Out" in the template light themselves when pressed,
            # so resend whatever the renderer wants for this control.
            self.invalidated.add(ev.control.id)
        dispatcher.dispatch(self, ev)
        # Aftertouch never changes an LED, and held pads send it continuously.
        if ev.kind != events.PRESSURE:
            self.dirty = True

    def on_refresh(self, flags):
        diagnostics.note("refresh flags 0x%X" % flags)
        self.dirty = True

    def on_idle(self):
        ui_commands.run_menu_commands(self.state)
        self._render_if_due()
        diagnostics.tick(self)

    def _render_if_due(self):
        if not self.dirty:
            return
        # While FL is busy (a modal dialog, the plugin picker, a channel being added), reading
        # channel and plugin state can be unsafe. Stay dirty and try again on the next idle.
        if not _safe_to_edit():
            if not self.unsafe_noted:
                diagnostics.note("render skipped: FL not safe to edit")
                self.unsafe_noted = True
            diagnostics.count("render_skipped")
            return
        if self.unsafe_noted:
            diagnostics.note("FL safe again: catching up on the skipped render")
            self.unsafe_noted = False
        # Clear first: an event arriving during the render sets it again for the next idle.
        self.dirty = False
        invalidated, self.invalidated = self.invalidated, set()
        for control_id in invalidated:
            self.leds.invalidate(control_id)
        self.render()

    def render(self):
        """Read FL's state and update every LED. Only called from OnInit and OnIdle."""
        began = diagnostics.clock()
        fl = FlSnapshot.read()
        self.fl = fl
        pads.follow_fpc_selection(self.state, fl)
        self.leds.write(renderer.render(self.state, fl))
        diagnostics.rendered(diagnostics.clock() - began)


def _safe_to_edit():
    """general.safeToEdit() (API 29) where it exists; older FL versions are assumed safe."""
    check = getattr(general, "safeToEdit", None)
    return True if check is None else bool(check())
