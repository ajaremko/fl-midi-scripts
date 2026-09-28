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
