"""
Pattern buttons. Named pattern_controls so it does not shadow FL Studio's patterns module.
"""

import midi
import patterns

from .common import on_press


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
