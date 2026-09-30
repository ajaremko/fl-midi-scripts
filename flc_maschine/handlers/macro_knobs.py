"""
E9-E16 (knob page 2): macros, whose meaning follows the focused plugin. The display labels are
fixed ("Macro 1" ... "Macro 8"); FL's hint bar names the parameter and shows its value.

The target, as the FLkey chooses it: a focused mixer effect (mixer.getActiveEffectIndex), else the
selected channel's plugin, else a Sampler, Audio Clip or Layer channel, whose macros are channel
REC events. What each knob controls comes from macros.py.

Plugin parameters are set with plugins.setParamValue (0-1, no pickup: the knobs are relative).
Each knob keeps a running value per parameter, so small steps add up on stepped parameters
(switches, selectors); it starts again from the plugin's value if that was changed elsewhere. The
first write to a parameter writes its current value first, because FL ignores the first
setParamValue on a freshly loaded plugin. Only knob turns call getParamName (never OnRefresh):
it triggers a focused-window refresh.
"""

import channels
import general
import midi
import mixer
import plugins
import ui

from .. import events, log, macros
from .channel_knobs import SET_FLAGS

MACRO_STEP = 1.0 / 128  # of a parameter's range, per encoder step
KNOB_INDEX = {"E%d" % (9 + i): i for i in range(8)}  # E9 is Macro 1
DUMP_LIMIT = 128  # parameters logged for a plugin without macros
SCAN_LIMIT = 4096  # parameters searched when matching names (some plugins have thousands)

# Channel types without a plugin, whose macros are channel REC events (FL's CT_ constants).
CHANNEL_TYPES = {
    getattr(midi, "CT_Sampler", 0): "Sampler",
    getattr(midi, "CT_Layer", 3): "Layer",
    getattr(midi, "CT_AudioClip", 4): "Audio Clip",
}


def _target():
    """(kind, index, slot, name) for what the macros act on, or None."""
    effect = mixer.getActiveEffectIndex()
    if effect is not None:
        track, slot = effect
        if plugins.isValid(track, slot):
            return "plugin", track, slot, plugins.getPluginName(track, slot)
    channel = channels.selectedChannel(1)  # -1 when no channel is selected
    if channel < 0:
        return None
    if plugins.isValid(channel):
        return "plugin", channel, -1, plugins.getPluginName(channel)
    kind = CHANNEL_TYPES.get(channels.getChannelType(channel))
    if kind is not None:
        return "channel", channel, -1, kind
    return None


def turn(controller, ev):
    """A macro knob turned: step its parameter on the focused plugin."""
    if ev.kind != events.TURN:
        return
    target = _target()
    if target is None:
        ui.setHintMsg("No plugin for macros")
        return
    kind, index, slot, name = target
    knob = KNOB_INDEX[ev.control.id]
    mapping = (macros.CHANNEL_MACROS if kind == "channel" else macros.MACROS).get(name)
    if not mapping:
        ui.setHintMsg("No macros for %s" % name)
        if kind == "plugin":
            _log_parameters(controller.state, index, slot, name)
        return
    entry = mapping[knob] if knob < len(mapping) else None
    if entry is None:
        ui.setHintMsg("Macro %d: not used on %s" % (knob + 1, name))
        return
    if kind == "channel":
        _step_channel(index, entry, ev.delta)
        return
    param = _resolve(controller.state, index, slot, name, entry, knob)
    if param is not None:
        _step_plugin(controller.state, index, slot, param, ev.delta)


def _step_channel(channel, offset, delta):
    event_id = channels.getRecEventId(channel) + offset
    value = channels.incEventValue(event_id, delta, midi.EKRes)
    general.processRECEvent(event_id, value, SET_FLAGS)  # FL's hint shows the parameter


def _resolve(state, index, slot, name, param_name, knob):
    """The index of a mapped parameter, None (and a hint) if missing. A name is looked up once per
    plugin; a number is the parameter's index, used where names repeat or change with the preset."""
    if isinstance(param_name, int):
        if 0 <= param_name < plugins.getParamCount(index, slot):
            return param_name
        _missing(state, name, param_name, knob)
        return None
    names = state.macro_params.get(name)
    if names is None:
        names = {}
        for i in range(min(plugins.getParamCount(index, slot), SCAN_LIMIT)):
            names.setdefault(plugins.getParamName(i, index, slot).strip().lower(), i)
        state.macro_params[name] = names
    param = names.get(param_name.strip().lower())
    if param is None:
        _missing(state, name, param_name, knob)
    return param


def _missing(state, name, param_name, knob):
    message = "Macro %d: no parameter %r on %s" % (knob + 1, param_name, name)
    ui.setHintMsg(message)
    if (name, param_name) not in state.macro_logged:
        state.macro_logged.add((name, param_name))
        log.info(message)


def _step_plugin(state, index, slot, param, delta):
    key = (index, slot, param)
    current = plugins.getParamValue(param, index, slot)
    running = state.macro_values.get(key)
    if running is None:
        plugins.setParamValue(current, param, index, slot, midi.PIM_None)  # FL ignores a first write
        target = current
    elif abs(current - running[1]) > 1e-6:
        target = current  # changed elsewhere: start again from the plugin's value
    else:
        target = running[0]
    target = max(0.0, min(1.0, target + delta * MACRO_STEP))
    plugins.setParamValue(target, param, index, slot, midi.PIM_None)
    # Keep the target and what FL made of it: stepped parameters only move once the target
    # reaches the next step.
    state.macro_values[key] = (target, plugins.getParamValue(param, index, slot))
    ui.setHintMsg("%s: %s" % (plugins.getParamName(param, index, slot).strip(),
                              plugins.getParamValueString(param, index, slot)))


def _log_parameters(state, index, slot, name):
    """Log a plugin's parameter list once per session, to write its macros from."""
    if name in state.macro_logged:
        return
    state.macro_logged.add(name)
    count = plugins.getParamCount(index, slot)
    log.info("No macros for %s yet. Its parameters (%d; first %d shown), for macros.py:"
             % (name, count, min(count, DUMP_LIMIT)))
    for i in range(min(count, DUMP_LIMIT)):
        param_name = plugins.getParamName(i, index, slot).strip()
        if param_name:
            log.info("  %d: %s" % (i, param_name))
