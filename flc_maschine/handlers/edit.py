"""
Editing actions for the shift-mode pads: Undo, Redo and Quantize.
"""

import channels
import general

from .common import on_press


@on_press
def undo(controller, ev):
    general.undoUp()  # one step back in the undo history


@on_press
def redo(controller, ev):
    general.undoDown()  # one step forward


@on_press
def quantize(controller, ev):
    """Quick-quantize the selected channel's notes (note starts only).

    FL's scripting API can only quantize a whole channel, at full strength.
    """
    channel = channels.selectedChannel(1)  # -1 when no channel is selected
    if channel >= 0:
        channels.quickQuantize(channel, 1)
