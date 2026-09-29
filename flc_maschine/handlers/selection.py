"""
Drag selection: turning the master encoder while it is pushed in selects a range of channels
(Channel Rack focused) or mixer tracks (Mixer focused). The first turn starts the range at the
selected channel or current track; each encoder message then moves the range's other end one step.
encoder.turn calls drag() while the push is held; encoder.push ends the drag on release.
"""

import channels
import midi
import mixer
import ui


def _set_channel(index, on):
    channels.selectChannel(index, 1 if on else 0)


def _set_track(index, on):
    # selectTrack only toggles, so only call it when the track's selection has to change.
    if bool(mixer.isTrackSelected(index)) != on:
        mixer.selectTrack(index)


class _Target:
    """How to select within one window: where a range starts, how many items there are, how to
    select one item exclusively, and how to (de)select one item."""

    def __init__(self, anchor, count, select_only, set_selected, hint):
        self.anchor = anchor
        self.count = count
        self.select_only = select_only
        self.set_selected = set_selected
        self.hint = hint  # (low, high) -> hint text


TARGETS = {
    midi.widChannelRack: _Target(
        anchor=lambda: max(0, channels.selectedChannel(1)),  # -1 when none: start at channel 0
        count=channels.channelCount,
        select_only=channels.selectOneChannel,
        set_selected=_set_channel,
        hint=lambda low, high: "Select: channels %d-%d" % (low + 1, high + 1),  # 1-based, as FL shows them
    ),
    midi.widMixer: _Target(
        anchor=mixer.trackNumber,
        # trackCount includes Master (0) and the "Current" utility track (last), which is left out.
        count=lambda: mixer.trackCount() - 1,
        select_only=mixer.setActiveTrack,
        set_selected=_set_track,
        hint=lambda low, high: "Select: mixer tracks %d-%d" % (low, high),  # insert numbers; Master is 0
    ),
}


def _focused_target_window():
    for window in TARGETS:
        if ui.getFocused(window):
            return window
    return None


def drag(state, delta):
    """Handle a turn while the encoder is pushed. Returns False if no drag applies (a popup menu is
    open, or neither the Channel Rack nor the Mixer is focused), so the turn is handled as usual."""
    if state.drag_window is None:
        if ui.isInPopupMenu():
            return False
        window = _focused_target_window()
        if window is None:
            return False
        anchor = TARGETS[window].anchor()
        TARGETS[window].select_only(anchor)
        state.drag_window = window
        state.drag_anchor = state.drag_end = anchor

    target = TARGETS[state.drag_window]
    anchor, end = state.drag_anchor, state.drag_end
    new_end = max(0, min(target.count() - 1, end + (1 if delta > 0 else -1)))
    if new_end != end:
        # Only the item joining or leaving the range changes: moving away from the anchor selects
        # the new end, moving back towards it deselects the old one.
        if abs(new_end - anchor) > abs(end - anchor):
            target.set_selected(new_end, True)
        else:
            target.set_selected(end, False)
        state.drag_end = new_end
    ui.setHintMsg(target.hint(min(anchor, new_end), max(anchor, new_end)))
    return True
