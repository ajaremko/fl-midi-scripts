"""
Solo and Mute: act on the selected Channel Rack channel, whichever window is focused. The
renderer lights each button while the selected channel is soloed or muted.
"""

import channels

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
