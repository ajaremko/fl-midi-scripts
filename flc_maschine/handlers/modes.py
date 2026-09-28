"""
Handlers that change the controller's own modes rather than FL Studio.
"""

from .common import on_press


def toggle(mode):
    """Turn a global mode (state.SHIFT or state.NEW) on, replacing any other, or off if it is on.

    Entering a mode also turns off any encoder override.
    """

    @on_press
    def handler(controller, ev):
        state = controller.state
        state.mode = None if state.mode == mode else mode
        if state.mode:
            state.encoder_mode = None

    return handler


def once(handler):
    """Wrap a mode-layer handler so the mode turns off after it runs on a press (one-shot)."""

    def wrapped(controller, ev):
        handler(controller, ev)
        if ev.is_press:
            controller.state.mode = None

    return wrapped
