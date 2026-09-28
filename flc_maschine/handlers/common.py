"""
Building blocks for bindings. A handler is a function handler(controller, ev) where ev is an
events.ControlEvent. The dispatcher marks the MIDI event handled before calling it; a handler
that wants FL Studio to process the message as well calls ev.pass_to_fl().
"""

from .. import events, log


def unimplemented(description=""):
    """Placeholder for a README function that is not written yet. Logs presses, turns and values."""

    def handler(controller, ev):
        if ev.kind in (events.RELEASE, events.PRESSURE):
            return
        name = ev.control.id
        if controller.state.mode:
            name = controller.state.mode.upper() + "+" + name
        log.info("unimplemented:", name, '"%s"' % description if description else "(no function assigned)")

    handler.placeholder = True  # not a real function: modes don't highlight it
    return handler


def passthrough(controller, ev):
    """Hand the message to FL Studio unchanged, e.g. so pads play the selected channel."""
    ev.pass_to_fl()


def on_press(fn):
    """Wrap a handler so it only runs on presses."""

    def handler(controller, ev):
        if ev.is_press:
            fn(controller, ev)

    return handler
