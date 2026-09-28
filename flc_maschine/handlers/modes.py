"""
Handlers that change the controller's own modes rather than FL Studio.
"""

from .common import on_press


@on_press
def toggle_shift(controller, ev):
    controller.state.shift = not controller.state.shift
