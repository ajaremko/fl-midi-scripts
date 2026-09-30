"""
Color mode (F12): the pads offer 16 colours, and pressing one colours every selected Channel Rack
channel (channels.setChannelColor, 0xRRGGBB, as Mikey_Maschine does). FL's refresh then updates the
pads and Group buttons. The renderer lights the pads in these colours (renderer._color_mode_pads).
"""

import channels
import ui

from .common import on_press

# 16 hues evenly spaced round the colour wheel (22.5 degrees apart), pad 1 red onwards, at 85%
# saturation and 90% value. Written out rather than computed: colorsys may not be in FL's Python.
PALETTE = [
    0xE62222,  # 1: 0 degrees, red
    0xE66C22,  # 2: 22.5
    0xE6B522,  # 3: 45
    0xCDE622,  # 4: 67.5
    0x84E622,  # 5: 90
    0x3BE622,  # 6: 112.5
    0x22E653,  # 7: 135
    0x22E69C,  # 8: 157.5
    0x22E6E6,  # 9: 180, cyan
    0x229CE6,  # 10: 202.5
    0x2253E6,  # 11: 225
    0x3B22E6,  # 12: 247.5
    0x8422E6,  # 13: 270
    0xCD22E6,  # 14: 292.5
    0xE622B5,  # 15: 315
    0xE6226C,  # 16: 337.5
]


def pick(index):
    """A pad in Color mode: give every selected channel PALETTE[index]."""

    @on_press
    def handler(controller, ev):
        selected = [c for c in range(channels.channelCount()) if channels.isChannelSelected(c)]
        if not selected:
            ui.setHintMsg("No channel selected")
            return
        for channel in selected:
            channels.setChannelColor(channel, PALETTE[index])
        ui.setHintMsg("Channel colour: %d" % (index + 1))

    return handler
