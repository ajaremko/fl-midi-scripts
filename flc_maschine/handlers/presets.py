"""
F13/F14: step the selected channel's plugin to its previous or next preset (plugins.prevPreset /
nextPreset, as Novation and the KeyLab mk3 do).

FL changes presets asynchronously: straight after the call, getName(FPN_Preset) can still return
the old name, or "" (Komplete Kontrol's script found the same). So the handler only records the
channel and the old name, and show_preset_name, called from OnIdle, shows the new name once it
settles, or whatever FL reports after PRESET_WAIT_TICKS.
"""

import channels
import midi
import plugins
import ui

from .common import on_press

# OnIdle ticks to wait for the preset name to change before showing it anyway (about 0.2 s). A
# plugin with one preset, or a step that wraps round to the same name, never changes it.
PRESET_WAIT_TICKS = 20


def _preset_name(channel):
    return plugins.getName(channel, -1, midi.FPN_Preset)


def step(direction):
    """A handler that steps the selected channel's plugin one preset back (-1) or on (+1)."""

    @on_press
    def handler(controller, ev):
        channel = channels.selectedChannel(1)  # -1 when no channel is selected
        if channel < 0:
            ui.setHintMsg("No channel selected")
            return
        if not plugins.isValid(channel):
            ui.setHintMsg("No plugin on this channel")
            return
        if plugins.getPresetCount(channel) == 0:
            ui.setHintMsg("No presets")
            return
        old_name = _preset_name(channel)
        if direction < 0:
            plugins.prevPreset(channel)
        else:
            plugins.nextPreset(channel)
        controller.state.preset_hint = (channel, old_name, PRESET_WAIT_TICKS)

    return handler


def show_preset_name(state):
    """Called from OnIdle: show the new preset's name once FL reports it."""
    if state.preset_hint is None:
        return
    channel, old_name, ticks = state.preset_hint
    name = _preset_name(channel)
    if (name and name != old_name) or ticks <= 1:
        state.preset_hint = None
        ui.setHintMsg("Preset: %s" % (name or "(no name)"))
        return
    state.preset_hint = (channel, old_name, ticks - 1)
