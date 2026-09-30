"""
Channels pad mode: the pads are Channel Rack channels, up to 16 at a time (the focus).

- Pads: pad 1 (bottom-left) is the focus's first channel, running across then up, in pad-number
  order. A press plays C5 on that channel (channels.midiNoteOn) and, if no other channel pad is
  held, selects it exclusively, as the FLkey's channel pads do. The release ends the note on the
  same channel, even if the focus has moved since.
- Group buttons: jump the focus to fixed divisions: Group A is channels 1-16, B 17-32 ... H 113-128.
- Encoder: while the Channel Rack is focused, each turn message scrolls the focus by one channel,
  so it also reaches the positions between the divisions (encoder.turn calls scroll).
- A red box on the Channel Rack's channel names (ui.crDisplayRect) shows the focus for
  FOCUS_BOX_MS when it changes or the mode is entered (follow).

renderer._channel_pads lights each pad in its channel's colour, brighter when the channel is
selected, and the Group buttons the focus overlaps.
"""

import channels
import midi
import ui

from ..state import CHANNELS
from .common import on_press
from .pads import FIXED_VELOCITY
from .sequencer import FOCUS_BOX_MS

CHANNELS_PER_PAGE = 16  # pads, and channels per Group division
C5 = 60  # the note a pad plays: FL calls MIDI note 60 C5


def last_offset(count):
    """The furthest the focus can move: the start of the last Group division, 0 with no channels.
    The encoder reaches every position up to it, and the Group buttons never go past it."""
    return max(0, (count - 1) // CHANNELS_PER_PAGE * CHANNELS_PER_PAGE)


def _hint_range(offset, count):
    ui.setHintMsg("Channels %d-%d" % (offset + 1, min(offset + CHANNELS_PER_PAGE, count)))  # 1-based, as FL


def play(pad_index):
    """A pad: play C5 on its channel, selecting it if no other channel pad is held.

    Reads the channel count and the channel's global index from FL rather than the last render's
    snapshot, so a press straight after a scroll or a Group jump plays the channel the pads now
    show (see ARCHITECTURE's design rules)."""

    def handler(controller, ev):
        state = controller.state
        pad_id = ev.control.id
        if ev.is_press:
            channel = state.channel_offset + pad_index
            if channel >= channels.channelCount():
                return  # no channel on this pad: silent
            global_index = channels.getChannelIndex(channel)  # midiNoteOn takes a global index
            velocity = FIXED_VELOCITY if state.fixed_velocity else ev.value
            channels.midiNoteOn(global_index, C5, velocity)
            if not state.channel_held:
                channels.selectOneChannel(channel)
            state.channel_held[pad_id] = global_index
        elif ev.is_release:
            global_index = state.channel_held.pop(pad_id, None)
            if global_index is not None:
                channels.midiNoteOn(global_index, C5, 0)
        # Aftertouch is ignored. The event stays handled either way, so FL doesn't also play the
        # raw pad note on the selected channel.

    handler.plays_notes = True  # the MK2 bridge repeats these pads (bindings.pads_play_notes)
    return handler


def jump(group):
    """A Group button: move the focus to that group's 16 channels, if it has any."""

    @on_press
    def handler(controller, ev):
        state = controller.state
        count = channels.channelCount()
        offset = group * CHANNELS_PER_PAGE
        if offset >= count:
            ui.setHintMsg("No channels in Group %s" % "ABCDEFGH"[group])
            return
        state.channel_offset = offset
        state.channel_box = None  # show the red box, even for the focus already shown
        _hint_range(offset, count)

    return handler


def scrolls(state):
    """Whether the encoder scrolls the focus: Channels mode, with the Channel Rack focused and no
    popup menu open. Elsewhere it navigates as usual."""
    return state.pad_mode == CHANNELS and ui.getFocused(midi.widChannelRack) and not ui.isInPopupMenu()


def scroll(state, delta):
    """The encoder's turn in Channels mode: move the focus one channel, within 0 ... last_offset."""
    count = channels.channelCount()
    offset = max(0, min(last_offset(count), state.channel_offset + (1 if delta > 0 else -1)))
    if offset != state.channel_offset:
        state.channel_offset = offset
        state.channel_box = None
    if count:
        _hint_range(offset, count)


def follow(state, fl):
    """Called after each render's snapshot is read. Keeps the focus within the channels there are
    (after channels are deleted or the Channel Rack group changes), and draws the red box around
    the focused channels' names when Channels mode starts or the focus moves. Returns True when it
    moved the focus, so the controller reads the snapshot again for the channels now shown."""
    if state.pad_mode != CHANNELS:
        state.channel_box = None
        return False
    clamped = min(state.channel_offset, last_offset(fl.channel_count))
    moved = clamped != state.channel_offset
    state.channel_offset = clamped
    if state.channel_box == clamped:
        return moved
    state.channel_box = clamped
    if fl.channel_count and ui.getVisible(midi.widChannelRack):
        # Left and top, then a width and a height (see sequencer.follow). No steps: the names flag
        # highlights the channels' name buttons, as Novation's FLkey script does for its banks.
        height = min(CHANNELS_PER_PAGE, fl.channel_count - clamped)
        ui.crDisplayRect(0, clamped, 0, height, FOCUS_BOX_MS, midi.CR_HighlightChannelName | midi.CR_ScrollToView)
    return moved
