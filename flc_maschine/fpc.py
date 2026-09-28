"""
Reads the pad layout of the selected FPC: each pad's note, colour and whether it is empty.
This is the only module that queries FPC.
"""

import channels
import midi
import plugins

from . import log, notes

PLUGIN_NAME = "FPC"

# plugins.getPadInfo options (FL Studio manual, getPadInfo flags)
PAD_NOTE = 1
PAD_EMPTY = 3


class FpcPad:
    __slots__ = ("note", "color", "empty")

    def __init__(self, note, color, empty):
        self.note = note
        self.color = color & 0xFFFFFF  # 0xRRGGBB
        self.empty = bool(empty)


def selected_fpc_channel():
    """The selected channel if it is an FPC, else None."""
    channel = channels.selectedChannel(1)  # -1 when no channel is selected
    if channel >= 0 and plugins.isValid(channel) and plugins.getPluginName(channel) == PLUGIN_NAME:
        return channel
    return None


def read_pad(channel, fpc_pad):
    return FpcPad(
        plugins.getPadInfo(channel, -1, PAD_NOTE, fpc_pad),
        # Colour via getColor and GC_Semitone, which FPC implements for pad colours (Novation's
        # FLkey script does the same). getPadInfo's colour option returns identical values. In
        # testing, both return the same grey (0x9FA3A6) for every bank B pad (16-31); see
        # known-issues.md.
        plugins.getColor(channel, -1, midi.GC_Semitone, fpc_pad),
        plugins.getPadInfo(channel, -1, PAD_EMPTY, fpc_pad),
    )


def read_banks(channel):
    """Both banks' pads: [bank A pads, bank B pads], 16 each in MK2 pad order."""
    return [
        [read_pad(channel, notes.fpc_pad(bank, pad)) for pad in range(notes.FPC_PADS_PER_BANK)]
        for bank in range(2)
    ]


def log_colour_sources(channel):
    """Diagnostic: print each pad's colour from getPadInfo's colour option and from getColor."""
    log.info("FPC pad colours on channel %d: pad, getPadInfo(option 2), getColor(GC_Semitone)" % channel)
    for pad in range(2 * notes.FPC_PADS_PER_BANK):
        from_pad_info = plugins.getPadInfo(channel, -1, 2, pad) & 0xFFFFFF
        from_get_color = plugins.getColor(channel, -1, midi.GC_Semitone, pad) & 0xFFFFFF
        log.info("%2d  0x%06X  0x%06X%s" % (pad, from_pad_info, from_get_color, "" if from_pad_info == from_get_color else "  differs"))
