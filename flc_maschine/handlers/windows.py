"""
Window buttons (BROWSE, F1-F4): show and focus a window, or hide it if it is already focused.
"""

import ui

from .common import on_press


def toggle(window):
    @on_press
    def handler(controller, ev):
        if ui.getFocused(window):
            ui.hideWindow(window)
        else:
            ui.showWindow(window)
            ui.setFocused(window)

    return handler
