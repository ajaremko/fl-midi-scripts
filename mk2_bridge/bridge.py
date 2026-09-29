"""
MK2 bridge: a small program that sits between the Maschine MK2 and FL Studio.

    MK2 --USB--> bridge --> loopMIDI "MK2 Bridge In"  --> FL (the FL Complete MK2 Bridge script)
    MK2 <--USB-- bridge <-- loopMIDI "MK2 Bridge Out" <-- FL (LEDs, Note Repeat state, MIDI clock)

Everything the MK2 sends goes to FL, and everything FL sends goes to the MK2, with two exceptions:

- Note Repeat. While it is on, a held pad is replayed to FL: its raw note-on again at the repeat
  rate, and a note-off half a cell later. The script handles each repeat as an ordinary pad hit.
  While FL is playing (its MIDI clock arriving) hits are locked to FL's clock and song position;
  while stopped, a timer thread runs them at the tempo. This is why the bridge exists: FL scripts
  only get irregular OnIdle calls, too uneven for note repeat.
- Messages meant for the bridge are not passed on to the MK2: FL's MIDI clock and transport (from
  "Send master sync"), and the script's Note Repeat state on MIDI channel 16 (see NoteRepeater).

Runs on the Windows machine with FL Studio and the MK2, not in FL's embedded Python. Needs Python 3
with mido and python-rtmidi (pip install -r requirements.txt) and loopMIDI with the two ports above.
FL's MIDI settings must have the MK2's own ports disabled, so the bridge can open them. See the
README's "MK2 bridge" section.

    python bridge.py            run the bridge (Ctrl+C to stop)
    python bridge.py --list     list the MIDI ports mido can see
"""

import argparse
import logging
import math
import sys
import threading
import time

DEVICE_NAME = "Maschine MK2"  # substring of the MK2's own port names
TO_FL_NAME = "MK2 Bridge In"  # loopMIDI port FL reads the MK2 from (the script's input)
FROM_FL_NAME = "MK2 Bridge Out"  # loopMIDI port FL sends LEDs to (the script's output)

# Real-time and song position messages from FL's master sync. They mean nothing to the MK2; the
# clock and transport ones drive Note Repeat.
FL_ONLY_TYPES = frozenset(["clock", "start", "stop", "continue", "songpos", "active_sensing", "reset"])

# The script's messages to the bridge: control changes on MIDI channel 16, which the MK2 template
# never uses. Keep in step with flc_maschine/bridge_link.py.
CONTROL_CHANNEL = 15
CC_REPEAT = 1  # 0 off, 127 on
CC_RATE, CC_RATE_LSB = 2, 34  # repeat rate in MIDI clocks, applied on the LSB
CC_TEMPO, CC_TEMPO_LSB = 3, 35  # tempo x 10, applied on the LSB
CC_PLAYING = 4  # FL playing: 0 stopped, 127 playing
CC_NO_CLOCK = 126  # bridge -> script: FL is playing but no MIDI clock arrives
CC_HELLO = 127  # bridge -> script: the bridge started, send everything

CLOCKS_PER_BEAT = 24  # MIDI clock resolution
CLOCKS_PER_SONGPOS = 6  # song position pointer counts sixteenth notes
GATE = 0.5  # fraction of a repeat cell each hit sounds for
MIN_SPACING = 0.5  # never hit a pad again sooner than this fraction of a repeat interval
CLOCK_TIMEOUT = 0.25  # seconds without a clock before repeats fall back to the timer
# While FL plays, a press this soon after a grid line plays at once (it counts as that line);
# any later press is held back to the next grid line, so the first note is on the grid too.
GRACE_FRACTION = 0.125  # of the repeat interval...
GRACE_MAX = 0.030  # ...but at most this many seconds

# FL sends its clock once per audio buffer, so ticks arrive in clumps (up to a buffer late: about
# 10 ms at FL's default 512 samples). A delay-locked loop smooths them: each tick corrects a model
# of when ticks should arrive, and repeats play on the model's times, from the timer thread.
LOCK_TICKS = 24  # ticks (a beat) of fast locking after the clock starts
ALPHA_LOCK = 0.2  # phase correction per tick while locking...
ALPHA = 0.05  # ...and after; the tempo correction is ALPHA ** 2 / 4
SPC_LIMIT = 0.10  # the smoothed tick length stays within this fraction of the tempo's
MAX_AHEAD = 3  # ticks the model may run ahead of the last tick received (so a late tick doesn't delay a line)
TIMING_EVERY = 5.0  # seconds between --timing reports

# Pad pressure (poly aftertouch) is thinned before it goes to FL: the MK2 sends it densely for every
# held pad, and a burst of it while FL is busy (e.g. starting to record) overflows FL's MIDI input.
PRESSURE_INTERVAL = 0.01  # seconds: at most one pressure message per pad this often
FLOOD_WARN = 400  # messages to FL in one second above which the traffic is logged
FLOOD_LOG_EVERY = 60.0  # seconds between traffic warnings

log = logging.getLogger("mk2_bridge")


class PortError(Exception):
    pass


def find_port(names, wanted, exclude=()):
    """The one port name containing `wanted` (case-insensitive) and none of `exclude`."""
    wanted_l = wanted.lower()
    excluded = [e.lower() for e in exclude]
    matches = [
        name for name in names
        if wanted_l in name.lower() and not any(e in name.lower() for e in excluded)
    ]
    if len(matches) == 1:
        return matches[0]
    found = "\n  ".join(names) if names else "(none)"
    if not matches:
        raise PortError("no MIDI port matches %r. Ports found:\n  %s" % (wanted, found))
    raise PortError("more than one MIDI port matches %r: %s. Pass a longer name. Ports found:\n  %s"
                    % (wanted, ", ".join(matches), found))


class _Pad:
    """A held pad being repeated."""

    __slots__ = ("channel", "note", "velocity", "on", "last_hit_pos", "last_hit_time", "off_pos",
                 "next_hit", "off_at", "pending_first", "released")

    def __init__(self, channel, note, velocity, now, pending_first=False):
        self.channel = channel
        self.note = note
        self.velocity = velocity
        # The press was held back to the next grid line: nothing has sounded yet.
        self.pending_first = pending_first
        self.released = False  # released before its held-back first note played (a quick tap)
        self.on = not pending_first  # FL has the note on (the press was passed through)
        # When it last sounded (the press counts): clock position (clock mode) and time.
        self.last_hit_pos = None
        self.last_hit_time = float("-inf") if pending_first else now
        self.off_pos = None  # clock mode: position of the pending note-off
        # Timer mode: the times of the next hit and the pending note-off.
        self.next_hit = None
        self.off_at = None


class _TimingStats:
    """For --timing: the worst raw tick error and the worst smoothed correction in a period."""

    def __init__(self):
        self.started = None
        self.ticks = 0
        self.max_error = 0.0
        self.max_correction = 0.0

    def add(self, error, correction):
        self.ticks += 1
        self.max_error = max(self.max_error, abs(error))
        self.max_correction = max(self.max_correction, abs(correction))

    def report(self, now, bpm):
        if self.started is None:
            self.started = now
            return None
        if now - self.started < TIMING_EVERY or not self.ticks:
            return None
        line = "clock: %.1f BPM, tick jitter +/-%.1f ms, smoothed +/-%.1f ms (%d ticks)" % (
            bpm, self.max_error * 1000, self.max_correction * 1000, self.ticks)
        self.__init__()
        self.started = now
        return line


class NoteRepeater:
    """Note Repeat, as pure logic: no ports, threads or clock of its own, so it can be tested.

    `emit(kind, channel, note, velocity)` sends a note to FL ("note_on" or "note_off").
    `on_no_clock()` is called once per play when FL plays without sending a clock. Callers pass the
    current time (seconds, any monotonic origin) and must not call in from two threads at once.

    A pad never sounds twice within MIN_SPACING of an interval, and never twice at the same clock
    position. FL's loop wrap otherwise hits twice at once: the clock at the end of the bar is on a
    grid line, and so is song position 0 a few milliseconds later.

    FL's clock ticks don't play anything directly: FL sends them once per audio buffer, so they
    arrive in clumps. clock() only corrects a smoothed model of the clock (a delay-locked loop:
    anchor_pos/anchor_time and spc, the seconds per tick), and tick(), from the timer thread,
    advances a virtual position along the model and steps each position it crosses (_step).

    While FL's clock runs, the first note is quantized too. A press within the grace window after
    the latest grid line (GRACE_FRACTION of an interval, at most GRACE_MAX) plays at once and counts
    as that line. Any other press is held back and plays on the next grid line; a pad released
    before then (a quick tap) still plays that one note, and its release isn't passed on.
    """

    def __init__(self, emit, on_no_clock=None):
        self.emit = emit
        self.on_no_clock = on_no_clock
        self.enabled = False
        self.rate = 6  # MIDI clocks per repeat (a sixteenth note)
        self.bpm = 120.0
        self._rate_msb = 0
        self._tempo_msb = 0
        self.pads = {}  # (channel, note) -> _Pad
        self.position = 0  # clock position of the next clock, from FL's start and song position
        self.last_clock = None  # time the last clock arrived
        # The smoothed clock: tick anchor_pos is predicted at anchor_time, and each tick lasts spc.
        self.locked = False
        self.anchor_pos = 0
        self.anchor_time = 0.0
        self.spc = self._tempo_spc()
        self._lock_ticks = 0
        self._jumped = False  # a song-position jump since the last tick (see clock)
        self.vpos = None  # the last position stepped along the model
        self._timing = _TimingStats()
        self.stopped = False  # FL sent stop (and no start or continue since)
        self.playing = False  # FL is playing, as the script reports it (CC 4)
        self._play_seen = None  # when a repeat was first seen during this play
        self._warned = False  # the no-clock warning was given during this play

    # --- state from the script -------------------------------------------------------------

    def control_change(self, control, value):
        if control == CC_REPEAT:
            enabled = value >= 64
            if not enabled:
                self.stop_all()
            self.enabled = enabled
        elif control == CC_RATE:
            self._rate_msb = value
        elif control == CC_RATE_LSB:
            self.rate = max(1, (self._rate_msb << 7) | value)
            self._reschedule()
        elif control == CC_TEMPO:
            self._tempo_msb = value
        elif control == CC_TEMPO_LSB:
            bpm = ((self._tempo_msb << 7) | value) / 10.0
            if bpm > 0:
                self.bpm = bpm
                self.spc = self._tempo_spc()  # follow a tempo change at once
        elif control == CC_PLAYING:
            self.playing = value >= 64
            if not self.playing:
                self._play_seen = None
                self._warned = False

    def _reschedule(self):
        # A new rate while pads repeat on the timer: count the new interval from each pad's last
        # hit, not from a schedule made at the old rate. (In clock mode the next grid line of the
        # new rate simply comes next.)
        interval = self.interval()
        for pad in self.pads.values():
            if pad.next_hit is not None:
                pad.next_hit = pad.last_hit_time + interval
                pad.off_at = pad.last_hit_time + interval * GATE

    # --- pads ------------------------------------------------------------------------------

    def grace(self):
        """Seconds after a grid line within which a press still counts as that line."""
        return min(GRACE_FRACTION * self.interval(), GRACE_MAX)

    def pad_on(self, channel, note, velocity, now):
        """A pad pressed. Returns whether to pass the press to FL now; False holds it back to the
        next grid line."""
        if not self.enabled:
            return True
        key = (channel, note)
        if self.clocked(now) and self.locked:
            vp = self._virtual(now) + 1e-6
            if not self.pads or self.vpos is None or self.vpos < math.floor(vp) - 1:
                self.vpos = self._capped(math.floor(vp))  # nothing was stepping: start from here
            line = math.floor(vp / self.rate) * self.rate
            if (vp - line) * self.spc <= self.grace():
                pad = _Pad(channel, note, velocity, now)  # just after a line: it counts as that line
                pad.last_hit_pos = line
                pad.off_pos = line + self._gate_clocks()
                self.pads[key] = pad
                return True
            self.pads[key] = _Pad(channel, note, velocity, now, pending_first=True)
            return False
        pad = _Pad(channel, note, velocity, now)  # FL stopped: play at once, repeat from here
        interval = self.interval()
        pad.next_hit = now + interval
        pad.off_at = now + interval * GATE
        self.pads[key] = pad
        return True

    def pad_off(self, channel, note, now):
        """A pad released. Returns whether to pass the release to FL: only if its note is on."""
        key = (channel, note)
        pad = self.pads.get(key)
        if pad is None:
            return True
        if pad.pending_first:
            pad.released = True  # a quick tap: it still plays its one note on the grid line
            return False
        del self.pads[key]
        return pad.on

    def stop_all(self):
        """Stop every repeat, releasing any note that is on. A pad still held then passes its own
        release to FL, which ignores a note-off for a note that isn't on."""
        for pad in self.pads.values():
            self._off(pad)
        self.pads.clear()

    @property
    def busy(self):
        return bool(self.pads)

    def _spaced(self, pad, now):
        """Whether the pad's last hit is far enough back for another."""
        return now - pad.last_hit_time >= MIN_SPACING * self.interval()

    # --- FL's clock (clock mode) -------------------------------------------------------------

    def clocked(self, now):
        """Whether FL's clock is driving repeats: it's running and a clock arrived recently."""
        return (not self.stopped and self.last_clock is not None
                and now - self.last_clock <= CLOCK_TIMEOUT)

    def start(self):
        self.stopped = False
        self._unlock()
        self._jump(0)

    def cont(self):
        self.stopped = False
        self._unlock()  # relock on the next tick

    def stop(self):
        self.stopped = True
        self._unlock()

    def songpos(self, value):
        self._jump(value * CLOCKS_PER_SONGPOS)

    def _unlock(self):
        self.locked = False
        self.vpos = None

    def _jump(self, position):
        # A new song position (start, or a jump or loop). While locked, the model stays continuous
        # in time: the target position is due when the next tick was, so smoothing carries across
        # a loop point. A sounding note keeps the rest of its gate. The last hit's position is
        # kept, so a position re-sent where a pad just hit can't hit again, and the time spacing
        # covers a loop wrap.
        stepped = self.vpos + 1 if self.vpos is not None else self.position
        for pad in self.pads.values():
            if pad.off_pos is not None:
                pad.off_pos = position + max(0, pad.off_pos - stepped)
        if self.locked:
            self.anchor_time = self._predicted(self.position)
            self.anchor_pos = position
            self.vpos = position - 1
            self._jumped = True
        self.position = position

    def clock(self, now):
        """A tick from FL: correct the smoothed clock. Nothing plays here; tick() steps the model."""
        self.last_clock = now
        if self.stopped:
            return
        k = self.position
        self.position += 1
        if not self.locked:
            self.locked = True
            self._lock_ticks = 0
            self.spc = self._tempo_spc()
            self.anchor_pos, self.anchor_time = k, now
            if self.vpos is None:
                self.vpos = k - 1
            return
        predicted = self._predicted(k)
        error = now - predicted
        if self._jumped:
            self._jumped = False
            if abs(error) > 0.5 * self.spc:
                # The jump wasn't continuous in time (e.g. FL sent an extra tick at the loop
                # point): take this tick's time rather than slowly correcting a whole tick.
                # Ordinary jitter stays within half a buffer of the model, well inside this.
                self.anchor_pos, self.anchor_time = k, now
                return
        alpha = ALPHA_LOCK if self._lock_ticks < LOCK_TICKS else ALPHA
        self._lock_ticks += 1
        correction = alpha * error
        self.anchor_pos, self.anchor_time = k, predicted + correction
        base = self._tempo_spc()
        self.spc = max(base * (1 - SPC_LIMIT), min(base * (1 + SPC_LIMIT), self.spc + alpha * alpha / 4 * error))
        # The smoothed figure leaves out the first beat of fast locking, which isn't typical.
        self._timing.add(error, correction if self._lock_ticks > LOCK_TICKS else 0.0)

    def _tempo_spc(self):
        """Seconds per tick at the script's tempo."""
        return 60.0 / (self.bpm * CLOCKS_PER_BEAT)

    def _predicted(self, pos):
        return self.anchor_time + (pos - self.anchor_pos) * self.spc

    def _virtual(self, now):
        """Where the smoothed clock is at `now`, in ticks."""
        return self.anchor_pos + (now - self.anchor_time) / self.spc

    def _capped(self, pos):
        """No further than MAX_AHEAD past the last tick received."""
        return min(pos, self.position - 1 + MAX_AHEAD)

    def _advance(self, now):
        """Step every position the smoothed clock has crossed by `now`."""
        target = self._capped(math.floor(self._virtual(now) + 1e-6))  # a tick due exactly now counts
        if self.vpos is None or target - self.vpos > MAX_AHEAD + 2 * CLOCKS_PER_BEAT:
            self.vpos = target  # lost track (e.g. nothing was stepping): carry on from here
            return
        while self.vpos < target:
            self.vpos += 1
            self._step(self.vpos, now)

    def timing_report(self, now):
        """A --timing line every TIMING_EVERY seconds while the clock runs, else None."""
        return self._timing.report(now, 60.0 / (self.spc * CLOCKS_PER_BEAT))

    def _step(self, pos, now):
        """One clock position along the smoothed clock: grid-line hits, first notes, gates."""
        rate = self.rate
        on_line = pos % rate == 0
        for key, pad in list(self.pads.items()):
            pad.next_hit = pad.off_at = None  # timer mode starts afresh if the clock stops
            if on_line and pad.pending_first:
                self._first_hit(pad, now)
                pad.last_hit_pos = pos
                pad.off_pos = pos + self._gate_clocks()
            elif (on_line and not pad.released and pos != pad.last_hit_pos
                    and self._spaced(pad, now)):
                self._hit(pad, now)
                pad.last_hit_pos = pos
                pad.off_pos = pos + self._gate_clocks()
            elif pad.on and pad.off_pos is not None and pos >= pad.off_pos:
                self._off(pad)
                if pad.released:  # a quick tap's one note is done
                    del self.pads[key]
            elif pad.on and pad.off_pos is None:  # was on the timer: finish its gate on the clock
                pad.off_pos = pos + self._gate_clocks()

    def _gate_clocks(self):
        return max(1, int(self.rate * GATE))

    # --- timer (timer mode) -------------------------------------------------------------------

    def interval(self):
        """Seconds per repeat at the current tempo."""
        return self.rate / float(CLOCKS_PER_BEAT) * 60.0 / self.bpm

    def tick(self, now):
        """From the timer thread: play hits and note-offs that are due, unless the clock drives them."""
        if not self.pads:
            return
        self._check_clock(now)
        if self.clocked(now):
            if self.locked:
                self._advance(now)
            return
        interval = self.interval()
        for key, pad in list(self.pads.items()):
            pad.off_pos = None  # clock mode picks up afresh if the clock returns
            if pad.pending_first:
                # Held back for a grid line, but the clock stopped: play it now.
                self._first_hit(pad, now)
                pad.next_hit = now + interval
                pad.off_at = now + interval * GATE
                continue
            if pad.released:
                if pad.on and pad.off_at is not None and now >= pad.off_at:
                    self._off(pad)
                if not pad.on:
                    del self.pads[key]  # a quick tap's one note is done
                continue
            if pad.next_hit is None:  # the clock just stopped: keep the rhythm of the last hit
                pad.next_hit = pad.last_hit_time + interval
                pad.off_at = pad.last_hit_time + interval * GATE
            if now >= pad.next_hit and self._spaced(pad, now):
                self._hit(pad, now)
                pad.next_hit += interval
                if pad.next_hit <= now:  # fell behind: don't catch up in a burst
                    pad.next_hit = now + interval
                pad.off_at = now + interval * GATE
            elif pad.on and pad.off_at is not None and now >= pad.off_at:
                self._off(pad)

    def _check_clock(self, now):
        """Warn once per play if FL is playing and pads repeat but no clock has arrived."""
        if not self.playing or self._warned:
            return
        if self._play_seen is None:
            self._play_seen = now
        got_clock = self.last_clock is not None and self.last_clock >= self._play_seen
        if not got_clock and now - self._play_seen > CLOCK_TIMEOUT:
            self._warned = True
            if self.on_no_clock:
                self.on_no_clock()

    # --- notes -------------------------------------------------------------------------------

    def _first_hit(self, pad, now):
        """Play a held-back first note: the pad's press, on the grid line."""
        pad.pending_first = False
        self._hit(pad, now)

    def _hit(self, pad, now):
        self._off(pad)
        self.emit("note_on", pad.channel, pad.note, pad.velocity)
        pad.on = True
        pad.last_hit_time = now

    def _off(self, pad):
        if pad.on:
            self.emit("note_off", pad.channel, pad.note, 0)
            pad.on = False


class Bridge:
    """Routes messages between the MK2 and FL. `to_fl` and `to_device` send one message each;
    `make_message(type, **fields)` builds one (mido.Message in main).

    The MK2's port, FL's port and the timer thread each call in on their own thread, so every entry
    point holds `lock`: the repeater and the `to_fl` port are never used by two threads at once.

    Pad pressure is thinned on its way to FL (see PRESSURE_INTERVAL): a repeated value is dropped,
    and a pad sends at most one value per interval, the latest being sent by the timer when the
    interval is up. A return to 0 always goes at once. Traffic to FL is counted, and a second with
    more than FLOOD_WARN messages is logged, so an input overflow in FL can be traced.
    """

    def __init__(self, to_fl, to_device, make_message=None, trace=False, clock=time.perf_counter,
                 timing=False):
        self.to_fl = to_fl
        self.to_device = to_device
        self.make_message = make_message
        self.trace = trace
        self.timing = timing  # log the clock's jitter and the smoothed error (--timing)
        self.clock = clock
        self.lock = threading.Lock()
        self.repeater = NoteRepeater(self._emit, on_no_clock=self._no_clock)
        self._pressure = {}  # (channel, note) -> _Pressure
        self._window_start = None  # traffic count: start of the current second
        self._window_count = 0
        self._window_pressure = 0
        self._last_flood_log = None

    def from_device(self, msg):
        with self.lock:
            if msg.type in ("note_on", "note_off"):  # only the pads send notes
                now = self.clock()
                if msg.type == "note_on" and msg.velocity > 0:
                    forward = self.repeater.pad_on(msg.channel, msg.note, msg.velocity, now)
                else:
                    self._pressure.pop((msg.channel, msg.note), None)  # drop pending pressure
                    forward = self.repeater.pad_off(msg.channel, msg.note, now)
                if not forward:
                    return
            elif msg.type == "polytouch" and not self._pressure_due(msg, self.clock()):
                return
            if self.trace:
                log.info("MK2 -> FL  %s", msg)
            self._send(self.to_fl, msg, "FL")

    def from_fl(self, msg):
        with self.lock:
            if msg.type == "control_change" and msg.channel == CONTROL_CHANNEL:
                if self.trace:
                    log.info("FL -> bridge  %s", msg)
                self.repeater.control_change(msg.control, msg.value)
                return
            if msg.type in FL_ONLY_TYPES:
                self._sync(msg)
                return
            if self.trace:
                log.info("FL -> MK2  %s", msg)
            self._send(self.to_device, msg, "MK2")

    def _sync(self, msg):
        repeater = self.repeater
        if msg.type == "clock":
            repeater.clock(self.clock())
        elif msg.type == "start":
            repeater.start()
        elif msg.type == "continue":
            repeater.cont()
        elif msg.type == "stop":
            repeater.stop()
        elif msg.type == "songpos":
            repeater.songpos(msg.pos)

    def tick(self):
        """From the timer thread."""
        with self.lock:
            now = self.clock()
            self.repeater.tick(now)
            self._flush_pressure(now)
            if self.timing:
                report = self.repeater.timing_report(now)
                if report:
                    log.info("%s", report)

    @property
    def busy(self):
        """Whether the timer has work: pads repeating, or pad pressure waiting to go to FL."""
        with self.lock:
            return self.repeater.busy or any(p.pending is not None for p in self._pressure.values())

    def _pressure_due(self, msg, now):
        """Whether a pad pressure message goes to FL now. If not, the latest is kept for the timer."""
        key = (msg.channel, msg.note)
        rec = self._pressure.get(key)
        if rec is None:
            self._pressure[key] = _Pressure(msg.value, now)
            return True
        if msg.value == rec.value:
            rec.pending = None  # back to what FL already has
            return False
        if msg.value == 0 or now - rec.sent_at >= PRESSURE_INTERVAL:
            rec.value, rec.sent_at, rec.pending = msg.value, now, None
            return True
        rec.pending = msg
        return False

    def _flush_pressure(self, now):
        for rec in self._pressure.values():
            if rec.pending is not None and now - rec.sent_at >= PRESSURE_INTERVAL:
                msg, rec.pending = rec.pending, None
                rec.value, rec.sent_at = msg.value, now
                if self.trace:
                    log.info("MK2 -> FL  %s", msg)
                self._send(self.to_fl, msg, "FL")

    def hello(self):
        """Tell the script the bridge (re)started, so it sends its Note Repeat state."""
        with self.lock:
            self._send(self.to_fl, self.make_message(
                "control_change", channel=CONTROL_CHANNEL, control=CC_HELLO, value=127), "FL")

    def stop_all(self):
        with self.lock:
            self.repeater.stop_all()

    def _no_clock(self):
        # Called under the lock, from tick.
        log.warning("FL is playing but no MIDI clock arrives on %s: tick Send master sync on that "
                    "output. Repeats aren't locked to the song until then.", FROM_FL_NAME)
        self._send(self.to_fl, self.make_message(
            "control_change", channel=CONTROL_CHANNEL, control=CC_NO_CLOCK, value=127), "FL")

    def _emit(self, kind, channel, note, velocity):
        msg = self.make_message(kind, channel=channel, note=note, velocity=velocity)
        if self.trace:
            log.info("repeat -> FL  %s", msg)
        self._send(self.to_fl, msg, "FL")

    def _send(self, send, msg, where):
        # An exception here would be lost on a callback thread; log it and keep going.
        if where == "FL":
            self._count(msg)
        try:
            send(msg)
        except Exception:
            log.exception("could not send %s to %s", msg, where)

    def _count(self, msg):
        """Count traffic to FL per second, and log a second with more than FLOOD_WARN messages."""
        now = self.clock()
        if self._window_start is None or now - self._window_start >= 1.0:
            if self._window_count > FLOOD_WARN and (
                    self._last_flood_log is None or now - self._last_flood_log >= FLOOD_LOG_EVERY):
                log.warning("heavy MIDI to FL: %d msg/s (pad pressure %d). FL may report a MIDI input "
                            "overflow.", self._window_count, self._window_pressure)
                self._last_flood_log = now
            self._window_start, self._window_count, self._window_pressure = now, 0, 0
        self._window_count += 1
        if msg.type == "polytouch":
            self._window_pressure += 1


class _Pressure:
    """What FL has for one pad's pressure, and a newer value waiting for PRESSURE_INTERVAL."""

    __slots__ = ("value", "sent_at", "pending")

    def __init__(self, value, sent_at):
        self.value = value
        self.sent_at = sent_at
        self.pending = None


def _run_timer(bridge, stopping):
    """Timer thread: plays Note Repeat, along the smoothed clock while FL plays and on its own
    timing while stopped. Sleeps 1 ms while pads repeat (or pad pressure is waiting)."""
    while not stopping.is_set():
        bridge.tick()
        time.sleep(0.001 if bridge.busy else 0.02)


def _high_resolution_timer(enable):
    """On Windows, ask for 1 ms timer resolution so short sleeps are precise."""
    if sys.platform != "win32":
        return
    try:
        import ctypes

        winmm = ctypes.WinDLL("winmm")
        (winmm.timeBeginPeriod if enable else winmm.timeEndPeriod)(1)
    except Exception:
        log.warning("could not set the Windows timer resolution; repeats may be less even")


def _parse_args(argv):
    parser = argparse.ArgumentParser(description="Pass MIDI between the Maschine MK2 and FL Studio.")
    parser.add_argument("--list", action="store_true", help="list MIDI ports and exit")
    parser.add_argument("--device", default=DEVICE_NAME, help="part of the MK2's port name (default: %(default)s)")
    parser.add_argument("--to-fl", default=TO_FL_NAME, help="loopMIDI port FL reads from (default: %(default)s)")
    parser.add_argument("--from-fl", default=FROM_FL_NAME, help="loopMIDI port FL writes to (default: %(default)s)")
    parser.add_argument("--verbose", action="store_true", help="log every message passed through")
    parser.add_argument("--timing", action="store_true",
                        help="log FL's clock jitter and the smoothed error every %d s while it runs" % TIMING_EVERY)
    parser.add_argument("--log", metavar="FILE", help="write the log to FILE (useful with pythonw)")
    return parser.parse_args(argv)


def main(argv=None):
    args = _parse_args(sys.argv[1:] if argv is None else argv)
    logging.basicConfig(
        filename=args.log, level=logging.INFO, format="%(asctime)s %(message)s", datefmt="%H:%M:%S"
    )
    try:
        import mido
    except ImportError:
        log.error("mido is not installed. Run: pip install -r requirements.txt")
        return 1

    inputs, outputs = mido.get_input_names(), mido.get_output_names()
    if args.list:
        print("Inputs:\n  " + "\n  ".join(inputs or ["(none)"]))
        print("Outputs:\n  " + "\n  ".join(outputs or ["(none)"]))
        return 0

    bridge_ports = (args.to_fl, args.from_fl)
    try:
        device_in_name = find_port(inputs, args.device, exclude=bridge_ports)
        device_out_name = find_port(outputs, args.device, exclude=bridge_ports)
        to_fl_name = find_port(outputs, args.to_fl)
        from_fl_name = find_port(inputs, args.from_fl)
    except PortError as error:
        log.error("%s", error)
        return 1

    opened = []
    try:
        # Outputs first, so nothing arrives on an input before it can be passed on.
        device_out = mido.open_output(device_out_name)
        opened.append(device_out)
        to_fl = mido.open_output(to_fl_name)
        opened.append(to_fl)
        bridge = Bridge(to_fl.send, device_out.send, make_message=mido.Message, trace=args.verbose,
                        timing=args.timing)
        opened.append(mido.open_input(device_in_name, callback=bridge.from_device))
        opened.append(mido.open_input(from_fl_name, callback=bridge.from_fl))
    except Exception as error:  # e.g. FL still has the MK2's port open
        log.error("could not open the MIDI ports: %s", error)
        log.error("Is the MK2 disabled in FL's MIDI settings, and is another bridge already running?")
        for port in opened:
            port.close()
        return 1

    _high_resolution_timer(True)
    stopping = threading.Event()
    timer = threading.Thread(target=_run_timer, args=(bridge, stopping), name="note-repeat", daemon=True)
    timer.start()
    bridge.hello()
    log.info("bridge running: %s <-> %s / %s. Ctrl+C to stop.", device_in_name, to_fl_name, from_fl_name)
    log.info("hello sent: the FL script will send its Note Repeat state")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        pass
    finally:
        stopping.set()
        timer.join(1)
        bridge.stop_all()  # no hanging notes
        for port in opened:
            port.close()
        _high_resolution_timer(False)
        log.info("bridge stopped")
    return 0


if __name__ == "__main__":
    sys.exit(main())
