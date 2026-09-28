"""
Buttons that press a single FL Studio key or command, such as Menu (F5) and Esc (F6), optionally
choosing the command by the focused window, or that open a menu and then step through it.
"""

import transport
import ui

from .. import diagnostics
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


# How many OnIdle ticks to wait for a menu to open before dropping its queued commands, so they
# can't act on the focused window instead (about half a second).
MENU_WAIT_TICKS = 50


def open_menu_then(menu_command, then):
    """A handler that opens a menu, then sends the commands in `then` once it is open.

    The commands are queued on the controller state and sent one per OnIdle tick while FL reports
    a popup menu (see run_menu_commands), because the menu may not be open yet when this handler
    returns.
    """

    @on_press
    def handler(controller, ev):
        transport.globalTransport(menu_command, 1)
        controller.state.menu_commands = list(then)
        controller.state.menu_wait = MENU_WAIT_TICKS

    return handler


def run_menu_commands(state):
    """Called from OnIdle: send the next queued menu command once the menu is open."""
    if not state.menu_commands:
        return
    if ui.isInPopupMenu():
        command = state.menu_commands.pop(0)
        diagnostics.note("menu queue: sending command %d (%d left)" % (command, len(state.menu_commands)))
        transport.globalTransport(command, 1)
        return
    state.menu_wait -= 1
    if state.menu_wait <= 0:
        diagnostics.note("menu queue: menu never opened, dropping %d commands" % len(state.menu_commands))
        state.menu_commands = []
