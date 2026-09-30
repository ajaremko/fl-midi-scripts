"""
Mixer pad mode: the pads are 4 mixer tracks at a time (the focus), one column of 4 pads each, the
focus's first track on the left:

- top row (pads 13-16): select the track (mixer.setTrackNumber). While one select pad is held,
  pressing others adds or removes their tracks (mixer.selectTrack), to select several.
- 2nd row (pads 9-12): mute / unmute it (mixer.muteTrack)
- 3rd row (pads 5-8): arm it for disk recording (mixer.armTrack)
- bottom row (pads 1-4): routing to this track, from the selected tracks (route_sources). If they
  all send here already, a press removes those sends; otherwise it adds the missing ones, so the
  sources always end up alike. Other routes (e.g. to Master) stay. Master is never a source: FL
  doesn't route it into inserts.

The encoder scrolls the focus one track at a time while the Mixer is focused (encoder.turn calls
scroll), through every track. The Group buttons jump by blocks of 4 used tracks
(mixer_tracks.used_tracks): Group A to the 1st used track, B to the 5th ... H to the 29th, since
8 groups of 4 can't cover all 125 inserts. Knob page 2 follows the focus too (knob): E9-E12 are the
4 tracks' volumes and E13-E16 their pans, left to right like the columns. When the focus changes, a red box on the Mixer
(ui.miDisplayRect) outlines it and the Mixer scrolls to it (follow). renderer._mixer_pads lights
the pads.
"""

import channels
import general
import midi
import mixer
import ui

from .. import events
from ..state import MIXER
from . import mixer_tracks
from .channel_knobs import SET_FLAGS
from .common import on_press
from .sequencer import FOCUS_BOX_MS

TRACKS_SHOWN = 4  # columns of pads

# Each pad's role, by its row: pad index // 4 counts rows from the bottom (pads 1-4).
SELECT, MUTE, ARM, ROUTE = "select", "mute", "arm", "route"
ROLE_FOR_ROW = (ROUTE, ARM, MUTE, SELECT)


def column_and_role(pad_index):
    """The pad's column (0-3, left to right: the focused tracks) and role."""
    return pad_index % TRACKS_SHOWN, ROLE_FOR_ROW[pad_index // TRACKS_SHOWN]


def track_count():
    """Master and the inserts: trackCount() also counts the "Current" utility track, last."""
    return mixer.trackCount() - 1


def last_first(count):
    """The furthest the focus can move: its first track, with the last track in its last column."""
    return max(0, count - TRACKS_SHOWN)


def _name(track):
    return mixer.getTrackName(track)


def _hint_range(first, count):
    last = min(first + TRACKS_SHOWN, count) - 1
    ui.setHintMsg("Mixer: %s - %s" % (_name(first), _name(last)))


def route_sources():
    """The tracks a routing press routes from: the selected tracks, or the current track when none
    is selected, as FL treats it. Never Master: FL doesn't route it into inserts."""
    selected = [track for track in range(track_count()) if mixer.isTrackSelected(track)]
    if not selected:
        selected = [mixer.trackNumber()]
    return [track for track in selected if track != 0]


def pad(pad_index):
    """A pad in Mixer mode: its column's track, in its row's role."""
    column, role = column_and_role(pad_index)

    def handler(controller, ev):
        state = controller.state
        if role == SELECT and ev.is_release:
            state.mixer_select_held.discard(ev.control.id)
            return
        if not ev.is_press:
            return
        track = state.mixer_first + column
        if track >= track_count():
            return  # no track in this column
        if role == SELECT:
            if state.mixer_select_held:
                mixer.selectTrack(track)  # another select pad is held: add or remove this track
            else:
                mixer.setTrackNumber(track, midi.curfxScrollToMakeVisible)  # this track only
            state.mixer_select_held.add(ev.control.id)
        elif role == MUTE:
            mixer.muteTrack(track)
            ui.setHintMsg("%s: %s" % (_name(track), "muted" if mixer.isTrackMuted(track) else "unmuted"))
        elif role == ARM:
            mixer.armTrack(track)
            ui.setHintMsg("%s: %s" % (_name(track), "armed" if mixer.isTrackArmed(track) else "disarmed"))
        else:
            _route(state, track)

    return handler


def _route(state, track):
    """A routing pad: route the selected tracks to this track. If they all send here already,
    remove those sends; otherwise add the missing ones. Each route is set explicitly (not toggled),
    so a route FL refuses (a loop, say) doesn't stop the others."""
    sources = route_sources()
    if track in sources:
        ui.setHintMsg("%s is selected: select only the tracks to route to it" % _name(track))
        return
    if not sources:
        ui.setHintMsg("Select the tracks to route to %s (Master can't be routed)" % _name(track))
        return
    sending = [source for source in sources if mixer.getRouteSendActive(source, track)]
    on = len(sending) < len(sources)
    changing = [source for source in sources if source not in sending] if on else sources
    refused = 0
    for source in changing:
        # The manual says setRouteTo returns nothing; MackieCU treats a negative result as refused.
        result = mixer.setRouteTo(source, track, 1 if on else 0)
        if result is not None and result < 0:
            refused += 1
    who = _name(sources[0]) if len(sources) == 1 else "%d tracks" % len(sources)
    if refused == len(changing):
        ui.setHintMsg("Can't route %s to %s" % (who, _name(track)))
        return
    mixer.afterRoutingChanged()
    note = " (%d refused)" % refused if refused else ""
    ui.setHintMsg("%s -> %s: %s%s" % (who, _name(track), "on" if on else "off", note))


def knob(column, rec_offset):
    """E9-E16 in Mixer mode: step a focused track's volume (REC_Mixer_Vol) or pan (REC_Mixer_Pan).
    Mixer track parameters are REC events from the track's getTrackPluginId(track, 0), stepped and
    written as E1-E7 do channel settings, so FL moves its own control and shows the hint."""

    def handler(controller, ev):
        if ev.kind != events.TURN:
            return
        track = controller.state.mixer_first + column
        if track >= track_count():
            return  # no track in this column
        event_id = mixer.getTrackPluginId(track, 0) + rec_offset
        value = channels.incEventValue(event_id, ev.delta, midi.EKRes)
        general.processRECEvent(event_id, value, SET_FLAGS)
        controller.state.last_event_id = event_id  # for Shift + Sampling (Edit)

    return handler


def jump(group):
    """A Group button: move the focus to that group's block of 4 used tracks, starting at its first."""

    @on_press
    def handler(controller, ev):
        state = controller.state
        used = mixer_tracks.used_tracks()
        if group * TRACKS_SHOWN >= len(used):
            ui.setHintMsg("No used mixer tracks for Group %s" % "ABCDEFGH"[group])
            return
        count = track_count()
        state.mixer_first = min(used[group * TRACKS_SHOWN], last_first(count))
        state.mixer_box = None  # show the red box, even for the focus already shown
        _hint_range(state.mixer_first, count)

    return handler


def scrolls(state):
    """Whether the encoder scrolls the focus: Mixer mode, with the Mixer focused and no popup menu
    open. Elsewhere it navigates as usual."""
    return state.pad_mode == MIXER and ui.getFocused(midi.widMixer) and not ui.isInPopupMenu()


def scroll(state, delta):
    """The encoder's turn in Mixer mode: move the focus one track, within 0 ... last_first."""
    count = track_count()
    first = max(0, min(last_first(count), state.mixer_first + (1 if delta > 0 else -1)))
    if first != state.mixer_first:
        state.mixer_first = first
        state.mixer_box = None
    _hint_range(first, count)


def follow(state, fl):
    """Called after each render's snapshot is read. Outside Mixer mode, forgets the red box. In
    Mixer mode, keeps the focus within the tracks there are, and scrolls the Mixer to and draws
    the red box around the focused tracks when the mode starts or the focus moves. Returns True
    when it moved the focus, so the controller reads the snapshot again."""
    if state.pad_mode != MIXER:
        state.mixer_box = None
        return False
    clamped = min(state.mixer_first, last_first(fl.mixer_count))
    moved = clamped != state.mixer_first
    state.mixer_first = clamped
    if state.mixer_box == clamped:
        return moved
    state.mixer_box = clamped
    if fl.mixer_count and ui.getVisible(midi.widMixer):
        last = min(clamped + TRACKS_SHOWN, fl.mixer_count) - 1
        ui.miDisplayRect(clamped, last, FOCUS_BOX_MS)
        # Scroll the Mixer to the focus without touching the selection (setTrackNumber would):
        # to its last track, then back to its first, so all of it is on screen, as the FLkey does.
        ui.scrollWindow(midi.widMixer, last)
        ui.scrollWindow(midi.widMixer, clamped)
    return moved
