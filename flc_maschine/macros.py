"""
Macro mappings for E9-E16 (knob page 2, labelled "Macro 1" ... "Macro 8").

What the macros control depends on the focused plugin (see handlers/macro_knobs.py):
- MACROS: per plugin, keyed by the plugin's own name (plugins.getPluginName with userName=0),
  up to 8 parameters, one per knob. A name is matched against plugins.getParamName, ignoring case
  and surrounding spaces. A number is the parameter's index: use it where names repeat or change
  with the preset (FLEX's macros). None leaves a knob unused. The hint bar always shows FL's own
  name for the parameter.
- CHANNEL_MACROS: per channel type for channels without a plugin (Sampler, Audio Clip, Layer), up
  to 8 channel REC event offsets (midi.REC_Chan_...), one per knob.

An empty list means "no macros yet". Turning a macro knob on a plugin without macros logs that
plugin's parameter list to Script output, which is what a new entry is written from. These are our
own choices, not copied from any vendor script.
"""

MACROS = {
    # Macro 1-8, in knob order.
    "FL Keys": ["Release", "Hardness", "Muffle", "Stereo", "Detune", "Overdrive", "Pan/Tremolo", "LFO Rate"],
    # The first test subset. Each is filled in from its logged parameter list.
    "3x Osc": [
        "Osc 1 shape", "Osc 2 shape", "Osc 3 shape",
        "Osc 1 coarse pitch", "Osc 2 coarse pitch", "Osc 3 coarse pitch",
        "Osc 2 mix level", "Osc 3 mix level",
    ],
    # FLEX's own 8 macro knobs. By index: FL's names for them follow the preset ("Filter",
    # "Vibrato", ...), and two are "Not Used".
    "FLEX": [10, 11, 12, 13, 14, 15, 16, 17],
    "Fruity Reeverb 2": [],
    "Fruity Delay 3": [],
}

CHANNEL_MACROS = {
    # Which channel parameters these get is still to be agreed.
    "Sampler": [],
    "Audio Clip": [],
    "Layer": [],
}
