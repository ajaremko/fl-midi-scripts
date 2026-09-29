"""
Solo and Mute: act on the selected Channel Rack channel, whichever window is focused. The
renderer lights each button while the selected channel is soloed or muted.

Shift + Select (Events): open the selected channel's Piano Roll.
"""

import channels
import midi
import ui

from .common import on_press


@on_press
def solo(controller, ev):
    """Toggle solo on the selected channel (FL mutes every other channel while it is soloed)."""
    channel = channels.selectedChannel(1)  # -1 when no channel is selected
    if channel >= 0:
        channels.soloChannel(channel)


@on_press
def mute(controller, ev):
    """Toggle mute on the selected channel."""
    channel = channels.selectedChannel(1)
    if channel >= 0:
        channels.muteChannel(channel)



@on_press
def open_piano_roll(controller, ev):
    """Shift + Select (Events): the selected channel's notes in the Piano Roll (the manual's own
    ui.openEventEditor example). Nothing when no channel is selected."""
    channel = channels.selectedChannel(1)
    if channel >= 0:
        ui.openEventEditor(channels.getRecEventId(channel) + midi.REC_Chan_PianoRoll, midi.EE_PR)
