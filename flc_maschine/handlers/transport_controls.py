"""
Transport buttons: Restart, Play (shift: Metro), Rec (shift: Count-In) and Step Left / Right.

Named transport_controls so it does not shadow FL Studio's transport module.
"""

import general
import midi
import mixer
import transport
import ui

from .common import on_press


@on_press
def restart(controller, ev):
    transport.stop()
    transport.setSongPos(0)
    transport.start()


@on_press
def play(controller, ev):
    transport.start()  # toggles play / pause


@on_press
def record(controller, ev):
    transport.record()


@on_press
def toggle_song_mode(controller, ev):
    """Switch between pattern mode and song (Playlist) mode."""
    transport.setLoopMode()


@on_press
def metronome(controller, ev):
    transport.globalTransport(midi.FPT_Metronome, 1)


@on_press
def count_in(controller, ev):
    transport.globalTransport(midi.FPT_CountDown, 1)


# Snap modes measured in beats (divisor of ticks per beat) and in steps. FL Studio's default is
# four steps per beat; no API reports it, so a step is taken as a quarter beat.
STEPS_PER_BEAT = 4
_BEAT_DIVISORS = {
    midi.Snap_Beat: 1,
    midi.Snap_HalfBeat: 2,
    midi.Snap_ThirdBeat: 3,
    midi.Snap_FourthBeat: 4,
    midi.Snap_SixthBeat: 6,
    midi.Snap_Step: STEPS_PER_BEAT,
    midi.Snap_HalfStep: STEPS_PER_BEAT * 2,
    midi.Snap_ThirdStep: STEPS_PER_BEAT * 3,
    midi.Snap_FourthStep: STEPS_PER_BEAT * 4,
    midi.Snap_SixthStep: STEPS_PER_BEAT * 6,
}


def snap_ticks(snap_mode, ppq, ppb):
    """Size of one snap grid cell in ticks, for ticks per beat ppq and ticks per bar ppb.

    Line and Cell snap depend on the zoom level, so they, None and unknown modes use one step.
    """
    if snap_mode == midi.Snap_Bar:
        return max(1, ppb)
    return max(1, ppq // _BEAT_DIVISORS.get(snap_mode, STEPS_PER_BEAT))


def next_position(pos, size, direction):
    """The next grid line after pos (direction 1), or the one before it (direction -1)."""
    if direction > 0:
        return (pos // size + 1) * size
    offset = pos % size
    return max(0, pos - (offset if offset else size))


def _step(direction):
    size = snap_ticks(ui.getSnapMode(), general.getRecPPQ(), general.getRecPPB())
    # transport.getSongPos stays at 0 in Song mode while stopped, even after setSongPos or a
    # mouse click moves the playhead (FL Studio 2026; see known-issues.md). mixer.getSongTickPos
    # follows it, in the same absolute ticks setSongPos takes.
    pos = mixer.getSongTickPos()
    transport.setSongPos(next_position(pos, size, direction), midi.SONGLENGTH_ABSTICKS)


@on_press
def step_left(controller, ev):
    _step(-1)


@on_press
def step_right(controller, ev):
    _step(1)
