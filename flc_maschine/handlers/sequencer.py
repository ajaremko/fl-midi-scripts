"""
Sequencer pad mode: the pads program the selected Channel Rack channel's step sequencer, one page
of 16 steps at a time.

- Pads: one step each, in reading order. Step 1 is the top-left pad (pad 13) and step 16 the
  bottom-right (pad 4). A press turns the step on or off (channels.setGridBit), after saving an
  undo point, as the Fire and FLkey do.
- Group buttons: the page. Group A shows steps 1-16, B 17-32 ... H 113-128 (state.step_page).
- A red box on the Channel Rack (ui.crDisplayRect) shows the page for FOCUS_BOX_MS when a Group
  button is pressed, when the mode is entered and when the selected channel changes (follow).
- renderer._sequencer_pads lights the steps from the snapshot. While FL plays, OnIdle asks
  playhead_moved whether to render again, so the white playhead pad moves on.

The repo's undocumented-features.md (section 1) covers how the vendor scripts use these calls.
"""

import channels
import general
import midi
import mixer
import ui

from ..state import SEQUENCER
from .common import on_press

STEPS_PER_PAGE = 16
FOCUS_BOX_MS = 2000  # how long the red box shows: the manual's maximum for crDisplayRect

# Pad index (0 = pad 1, bottom-left) -> the step it shows within the page (0-15), in reading
# order: the top row (pads 13-16) holds steps 1-4 and the bottom row (pads 1-4) steps 13-16.
STEP_FOR_PAD = [(3 - index // 4) * 4 + index % 4 for index in range(STEPS_PER_PAGE)]


def page_range(page):
    """The first and last step of a page, counting from 1 as FL shows them."""
    first = page * STEPS_PER_PAGE + 1
    return first, first + STEPS_PER_PAGE - 1


def toggle_step(pad_index):
    """A pad: turn its step on the current page on or off, on the selected channel.

    Reads the step and the selected channel from FL rather than the last render's snapshot: just
    after a page change, or an edit made with the mouse, the snapshot can be stale and the toggle
    would go the wrong way. Step toggles are rare, unlike pad notes and aftertouch, which the
    snapshot rule protects (see ARCHITECTURE's design rules)."""

    @on_press
    def handler(controller, ev):
        channel = channels.selectedChannel(1)  # -1 when no channel is selected
        if channel < 0:
            ui.setHintMsg("No channel selected")
            return
        if not channels.isGridBitAssigned(channel):
            ui.setHintMsg("This channel has no step sequencer")
            return
        step = controller.state.step_page * STEPS_PER_PAGE + STEP_FOR_PAD[pad_index]
        general.saveUndo("MK2 step edit", midi.UF_PR)
        channels.setGridBit(channel, step, 0 if channels.getGridBit(channel, step) else 1)

    return handler


def select_page(page):
    """A Group button: show that page's steps on the pads, and the red box on the next render."""

    @on_press
    def handler(controller, ev):
        state = controller.state
        state.step_page = page
        state.step_box = None  # draw the box again, even for the page already shown
        ui.setHintMsg("Steps %d-%d" % page_range(page))

    return handler


def follow(state, fl):
    """Called after each render's snapshot is read: draw the red box around the pads' steps when
    Sequencer mode starts, the page changes or the selected channel changes. Only while the
    Channel Rack is visible, as the Fire does; flag CR_ScrollToView scrolls the steps into view."""
    if state.pad_mode != SEQUENCER:
        state.step_box = None
        return
    box = (fl.step_channel, state.step_page)
    if box == state.step_box:
        return
    state.step_box = box
    if fl.step_channel is None or not ui.getVisible(midi.widChannelRack):
        return
    # Left and top, then a width and a height: the vendor scripts all pass sizes, although the
    # manual calls the third and fourth arguments right and bottom.
    ui.crDisplayRect(state.step_page * STEPS_PER_PAGE, fl.step_channel, STEPS_PER_PAGE, 1,
                     FOCUS_BOX_MS, midi.CR_ScrollToView)


def watching_playhead(state, fl):
    """Whether the pads show a playhead that can move: Sequencer mode, with FL playing in pattern
    mode (in song mode FL's step position isn't the pattern's)."""
    return state.pad_mode == SEQUENCER and fl.playing and not fl.song_mode


def playhead_moved(fl):
    """Called from OnIdle while watching_playhead: whether the playhead has moved on since the last
    render (fl). One cheap call per idle, as the Fire, FLkey and KeyLab poll it."""
    return mixer.getSongStepPos() != fl.step_pos
