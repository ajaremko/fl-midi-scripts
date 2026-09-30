"""
Which note each pad plays. The eight pad groups cover MIDI notes 0-127 once, 16 notes each:
Group A plays 0-15, Group B 16-31, ... Group H 112-127. Middle C (60, C5 in FL Studio) is
Group D's pad 13.
"""

from . import controls

NOTES_PER_GROUP = 16

# Pad id -> 0-15, counting from the bottom-left pad.
PAD_INDEX = {control.id: index for index, control in enumerate(controls.PADS)}


def pad_note(pad_group, pad_index):
    """The note a pad plays in the chromatic layout."""
    return pad_group * NOTES_PER_GROUP + pad_index


# Pitch classes (note % 12) of a piano's black keys: C#, D#, F#, G#, A#. Keyboard mode lights them
# dimmer than the white keys.
BLACK_KEYS = frozenset((1, 3, 6, 8, 10))


def is_black_key(note):
    return note % 12 in BLACK_KEYS


def is_c(note):
    return note % 12 == 0


# While the selected channel is FPC, Group E plays FPC's bank A and Group F its bank B; the other
# groups are silent. FPC numbers its pads from the bottom left like the MK2, and bank B's pads
# follow bank A's (16-31).
FPC_BANK_FOR_GROUP = {4: 0, 5: 1}
FPC_PADS_PER_BANK = 16


def fpc_pad(bank, pad_index):
    return bank * FPC_PADS_PER_BANK + pad_index
