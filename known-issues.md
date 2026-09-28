# Known Issues

Problems we know about and have not fixed, usually because the cause is outside these scripts.

## Maschine MK2: FPC bank B pads show grey instead of their colours

**Observed:** 2026-09-28.

**Symptom.** While the selected channel is FPC, Group E's pads show bank A's pad colours correctly. Group F plays bank B's sounds correctly, but every lit pad shows the same light grey instead of bank B's colours.

**Cause: FL Studio does not report bank B's colours.** For FPC pads 16–31 (bank B), both colour calls return `0x9FA3A6` for every pad, whatever colour the pad has in FPC:

- `plugins.getPadInfo(channel, -1, 2, pad)`
- `plugins.getColor(channel, -1, midi.GC_Semitone, pad)`

Pads 0–15 (bank A) return their real colours from both calls. Excerpt of the diagnostic output:

```text
[FLC MK2] FPC pad colours on channel 19: pad, getPadInfo(option 2), getColor(GC_Semitone)
[FLC MK2]  0  0x4591A1  0x4591A1
[FLC MK2]  1  0xA14745  0xA14745
...
[FLC MK2] 15  0x45A17C  0x45A17C
[FLC MK2] 16  0x9FA3A6  0x9FA3A6
...
[FLC MK2] 31  0x9FA3A6  0x9FA3A6
```

**Ruled out**

- **The script.** Group F reads pads 16–31 ([notes.fpc_pad](flc_maschine/notes.py)), the renderer uses bank B's list, and the LED writer sends what it is given. `test_pads_show_fpc_colours` passes with distinct bank B colours.
- **The choice of FL call.** Both colour calls return identical values for all 32 pads.
- **FPC's displayed bank.** Showing bank B in FPC's window does not change what FL reports.

Bank B's **notes** and **empty** flags come back correctly from `plugins.getPadInfo`, so only colours are affected.

**Effect.** Group F's non-empty pads light grey. Nothing else is affected.

**Re-checking after an FL Studio update**

1. Set `DEBUG_FPC_COLORS = True` in [flc_maschine/log.py](flc_maschine/log.py) and reload the script.
2. Select another channel, then the FPC channel. The script prints both calls' colours for all 32 pads in VIEW > Script output.
3. If rows 16–31 show real colours, FL has fixed it and this issue can be closed. The script needs no change.

**Possible workarounds (not implemented)**

- Treat `0x9FA3A6` from pads 16–31 as "no colour" and light those pads in the channel colour.
- Give each bank B pad the colour of the matching bank A pad.

## FL Studio 2026: toggling record can crash FL when the record-options dialog opens

**Observed:** 2026-09-28, FL Studio 2026, when pressing REC on the Maschine MK2.

**Symptom.** Pressing REC makes FL Studio open its record-options dialog ("What would you like to record?"), and FL crashes. In FL Studio 2025 with the old MK2 script the dialog opened normally.

**Workaround.** Set a default recording option in FL Studio's recording settings, so the dialog does not open when recording starts. With a default set, toggling record works.

**Script-side mitigation (implemented 2026-09-28, not yet re-tested).** This script reads more FL state on every refresh than the old one, and refreshes fire while the dialog is open. The extra reads are the selected channel's colour, `plugins.isValid` and `plugins.getPluginName`, and FPC pad data. FL can be unsafe to query while a modal dialog is open. Novation's FLkey script checks `general.safeToEdit()` and suspends its reads and input while it returns false, refreshing everything afterwards. `MaschineMk2.render` now does the same: it skips FL reads while `safeToEdit()` is false and catches up from `OnIdle`. This may let the dialog open safely; test it by clearing the default recording option again.

## FL Studio 2026: `transport.getSongPos` doesn't follow the playhead in Song mode (worked around)

**Observed:** 2026-09-28, FL Studio 2026, while building Step Left / Right on the Maschine MK2.

**Symptom.** Stopped in Song mode, `transport.getSongPos()` returns 0 in every mode (ms, seconds, absolute ticks, bars, steps, ticks). `transport.getSongPosHint()` stays at `1:01:00`. This holds even after `transport.setSongPos()` or a mouse click has moved the playhead. Step Right therefore moved one step once and then kept asking for the same position. Pattern mode reads the position correctly, though sometimes a press late.

**Workaround in the script.** Step Left / Right read the position with `mixer.getSongTickPos()`, which follows the playhead in both Song and Pattern mode, in the same absolute ticks `transport.setSongPos(…, SONGLENGTH_ABSTICKS)` takes ([transport_controls.py](flc_maschine/handlers/transport_controls.py)). `arrangement.currentTime()` also follows it in Song mode.

**Related setup.** Step sizes come from FL's main snap (the toolbar snap, `ui.getSnapMode()`). The Playlist and Piano Roll have their own snap settings, which the API doesn't report. Set them to "Main", or FL may round the playhead to a different grid than the one the script steps by.

## No scripting API to add a channel (worked around)

**Observed:** 2026-09-28. FL Studio's MIDI scripting API has no function or transport command that adds a channel to the Channel Rack. `FPT_Insert` does nothing visible in any window, and the only documented alternative is `ui.showPicker` (the Plugin picker).

**Workaround in the script.** New + Browse drives FL's menus instead, as you would by hand: it opens the main menu (`FPT_Menu`) and then sends Right three times, which reaches FL's **Add** menu. The Rights are sent from `OnIdle` one at a time, only once FL reports the menu open. If the menu hasn't opened within about half a second they are dropped, so they can't move anything in the focused window ([ui_commands.py](flc_maschine/handlers/ui_commands.py)).

**Fragile.** This depends on FL's main menu layout. If an FL update adds, removes or reorders menus, New + Browse will land on the wrong menu. The fix is the direction and number of steps in the New-layer Browse binding in [bindings.py](flc_maschine/bindings.py).

## Investigating crashes

**Observed:** from 2026-09-28, FL Studio crashes fairly regularly with the MK2 script loaded. The crash often comes a few moments *after* recording MIDI notes, not during a button press.

**First crash log (2026-09-28).** About 55 seconds of use, including recording pad notes with fixed velocity on, then REC off.
- The last callback, a refresh (flags `0x120`: focused window and LEDs), had finished. The last line was a stats line from `OnIdle`, and FL crashed about 0.8 s later, outside any logged callback.
- No script errors, no slow callbacks apart from the stats walk, and no unsafe periods.
- Every stats line failed on `gc.get_objects()` with `SystemError: ... returned NULL without setting an exception`, from 5 seconds after start. Python raises this when its garbage collector meets an object whose C-level state is broken, so something in FL's embedded Python can't be walked safely. Python's automatic garbage collection walks the same objects, which fits crashes that happen "a few moments later" rather than on an action.
- The diagnostics no longer walk objects; they use cheap counters instead, and they log every full garbage collection (below).

**Generic-controller test.** With the MK2 set to FL's generic controller (no script), recording pad notes did not crash FL. That points to the script.

**Second crash log (2026-09-28).** Recorded pad notes, stopped, then turned the encoder through the Channel Rack.
- **Ruled out:**
  - A leak: `blocks` stays flat, state sizes stay tiny.
  - Garbage collection: `gc_collections` never changed, and no full collection ran.
  - Script exceptions, slow callbacks, unsafe periods: none.
- **Crash point:** the log ends on a channel-change refresh (`0x10120`) during the encoder turns. The next stats line never came.
- **Callbacks running at the same time.** One `OnMidiMsg` started while an `OnRefresh` was still starting (its `>` line came before OnRefresh's first statement). FL was running the two on different threads.
  - At the time, both rendered: they read channel and plugin state and wrote LEDs, possibly while FL was changing the selected channel. The pad handler also read plugin state in the MIDI callback.

**Fix (2026-09-28, to be confirmed).** All FL reads and LED output now happen only in `OnIdle`:
- `OnMidiMsg` and `OnRefresh` just mark the controller dirty.
- The pads use the last render's snapshot for FPC instead of querying FL.
- See the data-flow section of [ARCHITECTURE.md](ARCHITECTURE.md).

**Third crash log (2026-09-28).** FL crashed about 5 s after being minimized, with nothing being pressed.
- **Recording went better** after the fix above. `OnMidiMsg` still overlapped an `OnRefresh` once (thread `t38844` vs `t36212`), which is now harmless.
- **Ruled out again:** leaks (`blocks` flat) and garbage collection (`gc_collections` unchanged for 130 s: no collection ever ran). No exceptions, no slow calls, no unfinished callbacks.
- **The script was idle.** With nothing dirty, `OnIdle` calls no FL functions. The only work left was the 5-second stats line, which collected memory counters (`sys.getallocatedblocks`, `gc.get_count`, `gc.get_stats`) before writing anything.
- **All three crashes** happened within 5 s after the last written stats line, or before the next one was due. That fits a crash while collecting those counters (on FL's multi-threaded, embedded Python). It isn't proof, and FL crashed before the diagnostics existed.
- **Change:** memory counters and GC watching are now **off by default**. When switched on, the memory line is written after the stats line, so a crash while collecting them shows as a stats line with no `memory:` line.

**Crash log.** The script writes `flc_debug.log` in this folder, next to the entry script, one line at a time so it survives a crash ([diagnostics.py](flc_maschine/diagnostics.py)). The log is restarted each time the script loads.

- `> OnMidiMsg [t1234]`, `> OnRefresh [t…]`, … mark each FL callback as it starts, with the id of the thread FL called it on, and `< OnMidiMsg` as it returns (`OnIdle` is only counted). A `>` with no matching `<` at the end of the file is what was running when FL crashed. Different thread ids, or a second `>` before the first `<`, mean FL ran callbacks at the same time.
- `midi <CONTROL> <kind> <value>` is each decoded control message (aftertouch is only counted), and `refresh flags 0x…` is each refresh.
- `render skipped: FL not safe to edit` / `FL safe again` show FL's unsafe periods (dialogs, the plugin picker, adding channels).
- `slow <callback>: N ms` flags callbacks over 25 ms, and `! exception in …` gives a traceback.
- A `stats:` line every 5 seconds gives:
  - Call counts, renders and the slowest render.
  - State sizes (`held`, `sounding`, `menu_queue`, `leds`).
- **Optional, off by default** (`MEMORY_STATS` / `WATCH_GC` in `diagnostics.py`):
  - A `memory:` line after each stats line: `blocks` (Python's allocated memory blocks; steady growth would point to a leak), `gc_counts` and `gc_collections`.
  - `gc start gen2` / `gc stop gen2` around every full garbage collection.
  - Turn these on only to look for a leak (see the third crash log).

**After a crash**, send the last ~50 lines of `flc_debug.log` and a couple of earlier `stats:` lines. Say what you did just before (e.g. recorded notes).

**Mitigations already in place** for the suspected causes: no render on pad aftertouch, and no FL reads while `general.safeToEdit()` is false.

**Switching the log off.** Set `ENABLED = False` in `flc_maschine/diagnostics.py`.
