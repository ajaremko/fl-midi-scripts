"""
Buttons that press a single FL Studio key or command, such as Menu (F5) and Esc (F6), optionally
choosing the command by the focused window.
"""

import transport
import ui

from .common import on_press


def send(command):
    """A handler that sends one global transport command (midi.FPT_*) on each press."""

    @on_press
    def handler(controller, ev):
        transport.globalTransport(command, 1)

    return handler


def send_for_focus(default, by_window):
    """Like send, but by_window ({window: command}) overrides default while that window is focused."""

    @on_press
    def handler(controller, ev):
        command = default
        for window, window_command in by_window.items():
            if ui.getFocused(window):
                command = window_command
                break
        transport.globalTransport(command, 1)

    return handler
