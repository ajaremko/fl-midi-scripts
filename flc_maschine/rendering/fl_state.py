"""
A snapshot of the FL Studio state the renderer needs, read once per render. Keeping FL API calls
here leaves the renderer a pure function that can be tested without FL Studio.
"""

import channels
import midi
import mixer
import patterns
import transport
import ui

from .. import fpc
from ..handlers.sequencer import STEPS_PER_PAGE
from ..handlers import mixer_pads, mixer_tracks
from ..state import CHANNELS, MIXER, PADS, SEQUENCER

PADS_COUNT = 16  # pads, for Channels mode's focused channels
TRACKS_SHOWN = 4  # columns of pads, for Mixer mode's focused tracks

# Windows whose focus the renderer may show, checked in this order.
WINDOWS = (midi.widMixer, midi.widChannelRack, midi.widPlaylist, midi.widPianoRoll, midi.widBrowser)


class FlSnapshot:
    __slots__ = ("focused_window", "playing", "recording", "song_mode", "channel_color", "channel_solo",
                 "channel_muted", "fpc_channel", "fpc_banks", "tempo", "step_channel", "grid_assigned",
                 "steps", "step_pos", "pattern_steps", "channel_count", "rack_colors", "rack_selected",
                 "mixer_count", "mixer_used", "track_colors", "track_selected", "track_muted", "track_armed",
                 "mixer_sources", "track_sends")

    def __init__(self, focused_window=None, playing=False, recording=False, song_mode=False,
                 channel_color=None, channel_solo=False, channel_muted=False, fpc_channel=None,
                 fpc_banks=None, tempo=120.0, step_channel=None, grid_assigned=False,
                 steps=(False,) * STEPS_PER_PAGE, step_pos=-1, pattern_steps=0, channel_count=0,
                 rack_colors=(None,) * PADS_COUNT, rack_selected=(False,) * PADS_COUNT, mixer_count=0,
                 mixer_used=(), track_colors=(None,) * TRACKS_SHOWN, track_selected=(False,) * TRACKS_SHOWN,
                 track_muted=(False,) * TRACKS_SHOWN, track_armed=(False,) * TRACKS_SHOWN,
                 mixer_sources=(), track_sends=(0,) * TRACKS_SHOWN):
        self.focused_window = focused_window  # one of WINDOWS, or None
        self.playing = playing
        self.recording = recording
        self.song_mode = song_mode  # True in song (Playlist) mode, False in pattern mode
        self.channel_color = channel_color  # selected channel's colour as 0xRRGGBB, or None
        self.channel_solo = channel_solo  # selected channel is soloed
        self.channel_muted = channel_muted  # selected channel is muted (also while another is soloed)
        self.fpc_channel = fpc_channel  # selected channel if it is an FPC, else None
        self.fpc_banks = fpc_banks  # fpc.read_banks() of that FPC, else None
        self.tempo = tempo  # BPM, for the MK2 bridge's Note Repeat while FL is stopped (bridge_link.py)
        # Sequencer pad mode only (read when it's on): the selected channel or None, whether it has
        # a step grid, its 16 steps on the page the pads show (by step, not pad), FL's playhead
        # step (-1 when stopped) and the current pattern's length in steps.
        self.step_channel = step_channel
        self.grid_assigned = grid_assigned
        self.steps = steps
        self.step_pos = step_pos
        self.pattern_steps = pattern_steps
        # Channels pad mode only (read when it's on): the Channel Rack's channel count (current group)
        # and, for the 16 channels from the focus, each one's colour (0xRRGGBB, None past the last
        # channel) and whether it is selected.
        self.channel_count = channel_count
        self.rack_colors = rack_colors
        self.rack_selected = rack_selected
        # Mixer pad mode only (read when it's on): Master and the inserts; the tracks in use
        # (mixer_tracks.used_tracks); and, for the 4 tracks from the focus, each one's colour
        # (0xRRGGBB, None past the last track), selection, mute and arm; the tracks a routing press
        # routes from (mixer_pads.route_sources), and how many of them already send to each of the 4
        # (not counting the track itself).
        self.mixer_count = mixer_count
        self.mixer_used = mixer_used
        self.track_colors = track_colors
        self.track_selected = track_selected
        self.track_muted = track_muted
        self.track_armed = track_armed
        self.mixer_sources = mixer_sources
        self.track_sends = track_sends

    @classmethod
    def read(cls, state=None):
        """Read FL's state, and what the controller state's pad mode needs: FPC's pads only in Pads
        mode (the startup mode, and what no state means), the step sequencer only in Sequencer mode
        (its playhead makes a render per step), the focused channels only in Channels mode and the
        focused mixer tracks only in Mixer mode."""
        pad_mode = state.pad_mode if state is not None else PADS
        focused = None
        for window in WINDOWS:
            if ui.getFocused(window):
                focused = window
                break
        channel = channels.selectedChannel(1)  # -1 when no channel is selected
        fpc_channel = fpc.selected_fpc_channel() if pad_mode == PADS else None
        snapshot = cls(
            focused_window=focused,
            playing=bool(transport.isPlaying()),
            recording=bool(transport.isRecording()),
            song_mode=transport.getLoopMode() != midi.SM_Pat,
            channel_color=channels.getChannelColor(channel) & 0xFFFFFF if channel >= 0 else None,
            channel_solo=channel >= 0 and bool(channels.isChannelSolo(channel)),
            channel_muted=channel >= 0 and bool(channels.isChannelMuted(channel)),
            fpc_channel=fpc_channel,
            fpc_banks=fpc.read_banks(fpc_channel) if fpc_channel is not None else None,
            tempo=_bpm(mixer.getCurrentTempo(1)),
        )
        if pad_mode == SEQUENCER:
            snapshot._read_steps(channel, state.step_page)
        elif pad_mode == CHANNELS:
            snapshot._read_rack(state.channel_offset)
        elif pad_mode == MIXER:
            snapshot._read_mixer(state.mixer_first)
        return snapshot

    def _read_mixer(self, first):
        self.mixer_count = count = mixer.trackCount() - 1  # without the "Current" utility track
        self.mixer_used = tuple(mixer_tracks.used_tracks())
        shown = [track if track < count else None for track in range(first, first + TRACKS_SHOWN)]
        self.track_colors = tuple(None if t is None else mixer.getTrackColor(t) & 0xFFFFFF for t in shown)
        self.track_selected = tuple(t is not None and bool(mixer.isTrackSelected(t)) for t in shown)
        self.track_muted = tuple(t is not None and bool(mixer.isTrackMuted(t)) for t in shown)
        self.track_armed = tuple(t is not None and bool(mixer.isTrackArmed(t)) for t in shown)
        self.mixer_sources = sources = tuple(mixer_pads.route_sources())
        self.track_sends = tuple(0 if t is None else sum(1 for s in sources if s != t and mixer.getRouteSendActive(s, t))
                                 for t in shown)

    def _read_rack(self, channel_offset):
        self.channel_count = count = channels.channelCount()
        shown = range(channel_offset, channel_offset + PADS_COUNT)
        self.rack_colors = tuple(channels.getChannelColor(i) & 0xFFFFFF if i < count else None for i in shown)
        self.rack_selected = tuple(i < count and bool(channels.isChannelSelected(i)) for i in shown)

    def _read_steps(self, channel, step_page):
        self.step_pos = mixer.getSongStepPos()
        self.pattern_steps = patterns.getPatternLength(patterns.patternNumber())  # steps, not beats
        if channel < 0:
            return
        self.step_channel = channel
        self.grid_assigned = bool(channels.isGridBitAssigned(channel))
        if self.grid_assigned:
            first = step_page * STEPS_PER_PAGE
            self.steps = tuple(bool(channels.getGridBit(channel, first + offset)) for offset in range(STEPS_PER_PAGE))


def _bpm(value):
    """Tempo in BPM. Komplete Kontrol found getCurrentTempo's asInt argument works the reverse of
    the manual, so accept either form: BPM, or BPM x 1000."""
    value = float(value)
    return value / 1000.0 if value > 1000 else value
