"""
Pattern buttons: New + Scene (a new pattern), Duplicate, and the Pattern button's length override
(step_length, show_length). Named pattern_controls so it does not shadow FL Studio's patterns module.
"""

import general
import midi
import patterns
import ui

from .common import on_press

STEPS_PER_BEAT = 4  # FL's default step size: a 16th note

# patterns.setPatternLength needs MIDI scripting API 39.
NO_LENGTH_API = "Pattern length needs a newer FL Studio (MIDI scripting API 39)"


def steps_per_bar():
    """Steps in a bar of the project's time signature: 16 in 4/4."""
    return general.getRecPPB() // general.getRecPPQ() * STEPS_PER_BEAT


def show_length(state=None):
    """Show the current pattern's length in bars, in FL's hint bar. getPatternLength returns steps
    (the manual says beats; Sequencer mode's Group LEDs confirmed steps). Fractions are shown, so a
    wrong unit assumption in step_length would show up at once."""
    index = patterns.patternNumber()
    bars = patterns.getPatternLength(index) / float(steps_per_bar())
    text = ("%d" % bars) if bars == int(bars) else ("%.2f" % bars).rstrip("0")
    ui.setHintMsg("%s: %s bar%s" % (patterns.getPatternName(index), text, "" if bars == 1 else "s"))


def step_length(state, delta):
    """The Pattern button's override: lengthen or shorten the current pattern by one bar per encoder
    message, snapping to whole bars, never below one bar.

    Assumes setPatternLength takes steps, like getPatternLength, although the manual says beats for
    both (show_length's fractional bars would reveal it)."""
    set_length = getattr(patterns, "setPatternLength", None)
    if set_length is None:
        ui.setHintMsg(NO_LENGTH_API)
        return
    index = patterns.patternNumber()
    bar = steps_per_bar()
    length = patterns.getPatternLength(index)
    if delta > 0:
        bars = length // bar + 1
    else:
        bars = max(1, -(-length // bar) - 1)  # whole bars covering it, less one
    set_length(index, bars * bar)
    show_length(state)


@on_press
def new_pattern(controller, ev):
    """Jump to the next empty pattern, without asking for a name."""
    patterns.findFirstNextEmptyPat(midi.FFNEP_DontPromptName)


@on_press
def duplicate_pattern(controller, ev):
    """Clone the current pattern into a new pattern after it.

    clonePattern() clones the patterns selected in the Picker, and the current pattern isn't always
    selected, so select it first (as Novation's script does). clonePattern(index) would avoid this,
    but needs API 43.
    """
    current = patterns.patternNumber()
    if not patterns.isPatternSelected(current):
        patterns.jumpToPattern(current)
    patterns.clonePattern()
