"""
Routes a ControlEvent to the handler bound to its control.
"""

import traceback

from . import bindings, controls, events, log


def dispatch(controller, ev):
    state = controller.state
    control_id = ev.control.id

    if ev.is_release and control_id in state.held:
        # Send the release to whichever handler took the press, even if the layers changed since.
        # Otherwise toggling shift while a pad is held would swallow its note-off.
        handler = state.held.pop(control_id)
    elif ev.kind == events.PRESSURE and control_id in state.held:
        # Aftertouch belongs to the press too.
        handler = state.held[control_id]
    else:
        handler = bindings.lookup(state, control_id)
        # Only gate controls send a release; trigger and toggle buttons are never "held".
        if handler is not None and ev.is_press and ev.control.mode == controls.GATE:
            state.held[control_id] = handler

    if handler is None:
        log.info("no binding:", ev)
        ev.pass_to_fl()
        return

    ev.raw.handled = True
    try:
        handler(controller, ev)
    except Exception:
        log.info("handler failed:", ev)
        traceback.print_exc()
