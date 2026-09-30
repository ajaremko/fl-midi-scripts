"""
Sampling (Edison) and Shift + Sampling (Edit: the event editor).

- Sampling opens Edison with its Audio Logger preset (ui.launchAudioEditor), ready to record a
  mixer track's audio, as MackieCU, SSL and Mikey's Maschine script do. The track is the selected
  channel's (the instrument being played), or in Mixer pad mode the selected mixer track. If the
  track already has an Edison, that one is brought forward (mixer.focusEditor) instead: the
  launcher's "reuse" argument doesn't stop FL loading another Edison on every press.
- Shift + Sampling opens FL's event editor (ui.openEventEditor, EE_EE) on the parameter the last MK2
  knob turn changed: FL has no "last tweaked" getter, so channel_knobs.turn and mixer_pads.knob
  record the REC event they write in state.last_event_id. Before any knob is turned, the selected
  channel's volume.
"""

import channels
import midi
import mixer
import plugins
import ui

from ..state import MIXER
from .common import on_press
from .mixer_tracks import EFFECT_SLOTS

# Edison's preset for recording a mixer track, as the vendor scripts load it.
AUDIO_LOGGER = "AudioLoggerTrack.fst"


def _sampling_track(state):
    """The mixer track to sample: the selected mixer track in Mixer pad mode, otherwise the
    selected channel's track, or the selected mixer track when no channel is selected."""
    if state.pad_mode != MIXER:
        channel = channels.selectedChannel(1)  # -1 when no channel is selected
        if channel >= 0:
            return channels.getTargetFxTrack(channel)
    return mixer.trackNumber()


def _edison_slot(track):
    """The effect slot of an Edison already on the track, or None. Matches the plugin's own name,
    so a renamed Edison counts too."""
    for slot in range(EFFECT_SLOTS):
        if mixer.isTrackPluginValid(track, slot) and plugins.getPluginName(track, slot).lower() == "edison":
            return slot
    return None


@on_press
def sample(controller, ev):
    """Sampling: Edison on the track to sample. An Edison already on the track is brought forward;
    otherwise a new one is loaded with the Audio Logger preset, as the vendor scripts call it."""
    track = _sampling_track(controller.state)
    name = mixer.getTrackName(track)
    slot = _edison_slot(track)
    if slot is not None and hasattr(mixer, "focusEditor"):  # focusEditor: API 25
        mixer.focusEditor(track, slot)
        ui.setHintMsg("Edison on %s" % name)
        return
    ui.launchAudioEditor(False, "", track, AUDIO_LOGGER, "")
    ui.setHintMsg("Edison (Audio Logger) on %s" % name)


@on_press
def edit_last(controller, ev):
    """Shift + Sampling (Edit): the event editor for the last knob's parameter, else the selected
    channel's volume."""
    event_id = controller.state.last_event_id
    if event_id is None:
        channel = channels.selectedChannel(1)
        if channel < 0:
            ui.setHintMsg("No channel selected")
            return
        event_id = channels.getRecEventId(channel) + midi.REC_Chan_Vol
    ui.openEventEditor(event_id, midi.EE_EE)
