"""Stand-in for FL Studio's plugins module."""

import midi

names = {}  # channel index -> plugin name
effects = {}  # (track, slot) -> mixer effect plugin name
params = {}  # (index, slot) -> list of [name, value 0-1, steps or None]; steps quantizes values
set_calls = []  # (value, param, index, slot, pickupMode) passed to setParamValue
pads = {}  # channel index -> list of (note, colour 0xRRGGBB, empty) per FPC pad


def isValid(index, slotIndex=-1, useGlobalIndex=False):
    if slotIndex == -1:
        return 1 if index in names else 0
    return 1 if (index, slotIndex) in effects else 0


def getPluginName(index, slotIndex=-1, userName=0, useGlobalIndex=False):
    return names[index] if slotIndex == -1 else effects[(index, slotIndex)]


def getParamCount(index, slotIndex=-1, useGlobalIndex=False):
    return len(params.get((index, slotIndex), []))


def getParamName(paramIndex, index, slotIndex=-1, useGlobalIndex=False):
    return params[(index, slotIndex)][paramIndex][0]


def getParamValue(paramIndex, index, slotIndex=-1, useGlobalIndex=False):
    return params[(index, slotIndex)][paramIndex][1]


def getParamValueString(paramIndex, index, slotIndex=-1, useGlobalIndex=False):
    return "%d%%" % round(params[(index, slotIndex)][paramIndex][1] * 100)


def setParamValue(value, paramIndex, index, slotIndex=-1, pickupMode=0, useGlobalIndex=False):
    set_calls.append((value, paramIndex, index, slotIndex, pickupMode))
    param = params[(index, slotIndex)][paramIndex]
    steps = param[2]
    param[1] = round(value * steps) / float(steps) if steps else value


def getPadInfo(chanIndex, slotIndex=-1, paramOption=0, paramIndex=0, useGlobalIndex=False):
    # No colour option (2): the script reads pad colours with getColor.
    note, colour, empty = pads[chanIndex][paramIndex]
    return {1: note, 3: 1 if empty else 0}[paramOption]


def getColor(index, slotIndex=-1, flag=0, paramIndex=0, useGlobalIndex=False):
    assert flag == midi.GC_Semitone
    return pads[index][paramIndex][1]
