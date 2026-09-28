"""
Crash diagnostics: a log file that survives FL Studio crashing.

Script output is lost when FL crashes, so this writes to flc_debug.log in the FL Complete folder,
opening and closing the file for every line. The last lines before a crash show what the script
was doing. Every FL callback goes through run(); a stats line every STATS_INTERVAL seconds tracks
call rates, render times, state sizes and memory counters, so growth (a leak) or a flood shows up.
With WATCH_GC, full (generation 2) garbage collections are logged as they start and stop, so
a crash during one leaves a "gc start" line with no "gc stop". MEMORY_STATS and WATCH_GC are off
by default (see below).

Never call gc.get_objects() here: in FL Studio's embedded Python it fails with
"SystemError: ... returned NULL without setting an exception", and walking every object may itself
be unsafe. Use the cheap counters instead.

Temporary: set ENABLED = False once the crashes are understood. Nothing here may break the
script, so every file and FL call is wrapped in try/except.
"""

try:
    import os
except ImportError:  # pragma: no cover - FL's embedded Python should have os
    os = None
import time
import traceback

try:
    import gc
except ImportError:  # pragma: no cover
    gc = None

try:
    import sys
except ImportError:  # pragma: no cover
    sys = None

try:
    from _thread import get_ident as _thread_id
except ImportError:  # pragma: no cover
    def _thread_id():
        return 0

ENABLED = True

# Memory counters (sys.getallocatedblocks, gc.get_count/get_stats) and logging of full garbage
# collections. Off by default: three crash logs showed no leak and no garbage collections, and
# each crash fits the moment the next memory counters were being collected. Turn on only to
# look for a leak.
MEMORY_STATS = False
WATCH_GC = False

LOG_FILE = (
    os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "flc_debug.log")
    if os else "flc_debug.log"
)
MAX_BYTES = 2000000  # start the file again when it grows past this
SLOW_MS = 25.0  # log callbacks slower than this
STATS_INTERVAL = 5.0  # seconds between stats lines
QUIET = frozenset(["OnIdle"])  # callbacks that are counted but not written line by line

clock = time.time  # replaced in tests

_started = clock()
_last_stats = _started
_counts = {}
_renders = 0
_max_render_ms = 0.0


def _write(text, mode="a"):
    try:
        with open(LOG_FILE, mode) as f:
            f.write(text)
            too_big = f.tell() > MAX_BYTES
        if too_big:
            with open(LOG_FILE, "w") as f:
                f.write("(log restarted: it passed %d bytes)\n" % MAX_BYTES)
    except Exception:
        pass


def line(text):
    """Write one timestamped line."""
    if ENABLED:
        _write("+%9.3f %s\n" % (clock() - _started, text))


def note(text):
    """Extra detail from the script, such as the decoded MIDI control."""
    line(text)


def count(key):
    """Count something without writing a line (e.g. aftertouch messages)."""
    if ENABLED:
        _counts[key] = _counts.get(key, 0) + 1


def start():
    """Start a fresh log. Called when the script initialises."""
    global _started, _last_stats, _renders, _max_render_ms
    if not ENABLED:
        return
    _started = _last_stats = clock()
    _counts.clear()
    _renders = 0
    _max_render_ms = 0.0
    api = "?"
    try:
        import general

        api = general.getVersion()
    except Exception:
        pass
    _write("FL Complete MK2 debug log, started %s, FL scripting API %s\n"
           % (time.strftime("%Y-%m-%d %H:%M:%S"), api), mode="w")
    if MEMORY_STATS:
        line("memory at start: " + _memory())
    if WATCH_GC:
        _watch_gc()


def run(name, fn, *args):
    """Run an FL callback: count it, log it, time it, and log any exception before re-raising."""
    if not ENABLED:
        return fn(*args)
    _counts[name] = _counts.get(name, 0) + 1
    logged = name not in QUIET
    if logged:
        # The thread id shows callbacks FL runs at the same time; "<" marks the return, so a
        # crash inside a callback leaves a ">" line without its "<".
        line("> %s [t%d]" % (name, _thread_id()))
    began = clock()
    try:
        return fn(*args)
    except Exception:
        line("! exception in %s\n%s" % (name, traceback.format_exc()))
        raise
    finally:
        ms = (clock() - began) * 1000.0
        if ms > SLOW_MS:
            line("slow %s: %.1f ms" % (name, ms))
        if logged:
            line("< " + name)


def _memory():
    """Cheap memory counters that don't walk objects: allocated blocks (grows with a leak), the
    GC's pending counts per generation, and how many collections each generation has run."""
    parts = []
    try:
        parts.append("blocks=%d" % sys.getallocatedblocks())
    except Exception:
        parts.append("blocks=?")
    try:
        parts.append("gc_counts=%d/%d/%d" % gc.get_count())
        parts.append("gc_collections=" + "/".join(str(s.get("collections", "?")) for s in gc.get_stats()))
    except Exception:
        parts.append("gc=?")
    return " ".join(parts)


def _gc_callback(phase, info):
    """Called by Python around every garbage collection. Full (generation 2) collections are
    logged; younger ones happen constantly, so they are only counted."""
    try:
        generation = info.get("generation")
        if generation == 2:
            if phase == "start":
                line("gc start gen2")
            else:
                line("gc stop gen2: collected=%s uncollectable=%s"
                     % (info.get("collected"), info.get("uncollectable")))
        elif phase == "start":
            count("gc_gen%s" % generation)
    except Exception:
        pass


def _watch_gc():
    """Register _gc_callback once, even if the script is reloaded."""
    try:
        gc.callbacks[:] = [cb for cb in gc.callbacks if getattr(cb, "__name__", "") != "_gc_callback"]
        gc.callbacks.append(_gc_callback)
    except Exception:
        line("could not watch garbage collections")


def rendered(seconds):
    """Record one render and how long it took."""
    global _renders, _max_render_ms
    if ENABLED:
        _renders += 1
        _max_render_ms = max(_max_render_ms, seconds * 1000.0)


def tick(controller):
    """Called from OnIdle: write a stats line every STATS_INTERVAL seconds."""
    global _last_stats, _renders, _max_render_ms
    if not ENABLED:
        return
    now = clock()
    if now - _last_stats < STATS_INTERVAL:
        return
    _last_stats = now
    try:
        state = controller.state
        counts = " ".join("%s=%d" % item for item in sorted(_counts.items()))
        line("stats: %s | renders=%d max_render=%.1fms | held=%d sounding=%d menu_queue=%d leds=%d"
             % (counts, _renders, _max_render_ms, len(state.held), len(state.sounding),
                len(state.menu_commands), len(controller.leds._sent)))
        if MEMORY_STATS:
            # A separate line, written after the stats line: a crash while collecting the
            # counters leaves a stats line with no "memory:" line after it.
            line("memory: " + _memory())
    except Exception:
        line("stats failed:\n" + traceback.format_exc())
    _counts.clear()
    _renders = 0
    _max_render_ms = 0.0
