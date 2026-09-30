import device
import general
import ui

from . import bridge_link, diagnostics, dispatcher, events, feedback, log
from .handlers import channel_pads, pads, presets, sequencer, ui_commands
from .rendering import renderer
from .rendering.fl_state import FlSnapshot
from .rendering.output import LedWriter
from .state import ControllerState


# While Note Repeat is on in bridge mode, render every this many idles even if nothing marked the
# controller dirty, so snap or tempo changes FL makes without a refresh still reach the bridge.
BRIDGE_RECHECK_IDLES = 25


class MaschineMk2:
    def __init__(self, bridge=False):
        # bridge: running through the MK2 bridge (the Bridge entry script). Adds Note Repeat and
        # the channel-16 link that tells the bridge its state; see bridge_link.py.
        self.bridge = bridge
        # Stops a MIDI feedback loop (the script's output routed back into its input); see feedback.py.
        self.guard = feedback.FeedbackGuard(bridge)
        self.link = bridge_link.BridgeLink() if bridge else None
        self.idles = 0
        self.no_clock_warned = False
        self.state = ControllerState()
        self.leds = LedWriter(on_send=self.guard.sent)
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
        if self.link:
            self.link.invalidate()
        self.dirty = True
        self._render_if_due()

    def on_deinit(self):
        log.info("deinit")
        if self.guard.tripped:
            return  # send nothing into a feedback loop
        self.leds.write({})
        if self.link:
            self.state.note_repeat = 0  # note_repeat.OFF: tell the bridge to stop repeating
            self.link.write(self.state, self.fl)

    def on_midi_msg(self, event):
        log.trace_midi(event)
        if self.guard.tripped:
            event.handled = True  # a feedback loop: swallow everything until the script is reloaded
            return
        if self.link and bridge_link.is_hello(event):
            # The bridge (re)started: send it everything on the next render, LEDs included, in
            # case the MK2 behind it was reconnected.
            event.handled = True
            self.link.invalidate()
            self.leds.invalidate()
            self.dirty = True
            return
        if self.link and bridge_link.is_no_clock(event):
            event.handled = True
            if not self.no_clock_warned:  # once per session
                self.no_clock_warned = True
                log.info(bridge_link.NO_CLOCK_WARNING)
                ui.setHintMsg(bridge_link.NO_CLOCK_WARNING)
            return
        if feedback.is_channel_mode(event):
            # FL sends these (e.g. All Notes Off) on all 16 channels after an input overflow or a
            # panic. No MK2 control sends them: swallow them quietly.
            event.handled = True
            return
        if self.guard.check(event):
            event.handled = True
            log.info(feedback.WARNING, "(tripped by %s)" % feedback.describe(event))
            ui.setHintMsg(feedback.WARNING)
            return
        ev = events.decode(event)
        if ev is None:
            # Not from any MK2 control. Don't let FL act on it (as a note, or a CC such as volume).
            event.handled = True
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
        if self.link and self.state.note_repeat:
            self.idles += 1
            if self.idles >= BRIDGE_RECHECK_IDLES:
                self.idles = 0
                self.dirty = True
        ui_commands.run_menu_commands(self.state)
        presets.show_preset_name(self.state)
        # Sequencer mode's playhead: render when FL's step position moves on (no refresh says so).
        if not self.dirty and sequencer.watching_playhead(self.state, self.fl) and _safe_to_edit():
            if sequencer.playhead_moved(self.fl):
                self.dirty = True
        self._render_if_due()
        diagnostics.tick(self)

    def _render_if_due(self):
        if not self.dirty or self.guard.tripped:
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
        state = self.state
        fl = FlSnapshot.read(state.pad_mode, state.step_page, state.channel_offset)
        if channel_pads.follow(state, fl):
            # Channels mode's focus was past the last channel (channels deleted, or another Channel
            # Rack group): it moved back, so read the channels it now shows.
            fl = FlSnapshot.read(state.pad_mode, state.step_page, state.channel_offset)
        self.fl = fl
        pads.follow_fpc_selection(state, fl)
        sequencer.follow(state, fl)
        self.leds.write(renderer.render(self.state, fl))
        if self.link:
            self.link.write(self.state, fl)
        diagnostics.rendered(diagnostics.clock() - began)


def _safe_to_edit():
    """general.safeToEdit() (API 29) where it exists; older FL versions are assumed safe."""
    check = getattr(general, "safeToEdit", None)
    return True if check is None else bool(check())
