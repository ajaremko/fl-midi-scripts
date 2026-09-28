"""
A snapshot of the FL Studio state the renderer needs, read once per render. Keeping FL API calls
here leaves the renderer a pure function that can be tested without FL Studio.
"""

import channels
import midi
import transport
import ui

from .. import fpc

# Windows whose focus the renderer may show, checked in this order.
WINDOWS = (midi.widMixer, midi.widChannelRack, midi.widPlaylist, midi.widPianoRoll, midi.widBrowser)


class FlSnapshot:
    __slots__ = ("focused_window", "playing", "recording", "channel_color", "fpc_channel", "fpc_banks")

    def __init__(self, focused_window=None, playing=False, recording=False, channel_color=None,
                 fpc_channel=None, fpc_banks=None):
        self.focused_window = focused_window  # one of WINDOWS, or None
        self.playing = playing
        self.recording = recording
        self.channel_color = channel_color  # selected channel's colour as 0xRRGGBB, or None
        self.fpc_channel = fpc_channel  # selected channel if it is an FPC, else None
        self.fpc_banks = fpc_banks  # fpc.read_banks() of that FPC, else None

    @classmethod
    def read(cls):
        focused = None
        for window in WINDOWS:
            if ui.getFocused(window):
                focused = window
                break
        channel = channels.selectedChannel(1)  # -1 when no channel is selected
        fpc_channel = fpc.selected_fpc_channel()
        return cls(
            focused_window=focused,
            playing=bool(transport.isPlaying()),
            recording=bool(transport.isRecording()),
            channel_color=channels.getChannelColor(channel) & 0xFFFFFF if channel >= 0 else None,
            fpc_channel=fpc_channel,
            fpc_banks=fpc.read_banks(fpc_channel) if fpc_channel is not None else None,
        )
