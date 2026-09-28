"""Stand-in for FL Studio's plugins module."""

import midi

names = {}  # channel index -> plugin name
pads = {}  # channel index -> list of (note, colour 0xRRGGBB, empty) per FPC pad


def isValid(index, slotIndex=-1, useGlobalIndex=False):
    return 1 if index in names else 0


def getPluginName(index, slotIndex=-1, userName=0, useGlobalIndex=False):
    return names[index]


def getPadInfo(chanIndex, slotIndex=-1, paramOption=0, paramIndex=0, useGlobalIndex=False):
    # No colour option (2): the script reads pad colours with getColor.
    note, colour, empty = pads[chanIndex][paramIndex]
    return {1: note, 3: 1 if empty else 0}[paramOption]


def getColor(index, slotIndex=-1, flag=0, paramIndex=0, useGlobalIndex=False):
    assert flag == midi.GC_Semitone
    return pads[index][paramIndex][1]
