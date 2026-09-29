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

**Observed:** 2026-09-28, FL Studio 2026, when pressing REC on the Maschine MK2. **FL 2026 only**: not seen in FL Studio 2025.

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

## FL Studio 2026: FL hangs (stops responding) after recording, when leaving and returning to FL

**Observed:** 2026-09-28, FL Studio 2026 (FL64.exe 26.1.2.5557), with the MK2 script loaded alongside the Akai Fire and FLkey 2 scripts. **Not reproduced in FL Studio 2025**, with the same workflow and script. This is the second FL 2026-only problem, after the record-dialog crash above.

**Symptom.** A few moments after recording MIDI (often when switching to another window and back, or minimizing and restoring FL), FL stops responding and Windows ends it. It looks like a crash, but Windows records it as a hang: Event ID 1002, "Application Hang", **`HangType: Cross-thread`**. FL's main (UI) thread was stuck waiting on another thread.

**Findings from four script debug logs**
- **No script errors, no memory leak, no garbage collection.** Allocated memory stayed flat, and Python's collector never ran.
- **FL calls the script on two threads.** `OnMidiMsg` runs on one thread; `OnInit`, `OnRefresh` and (presumably) `OnIdle` on FL's UI thread. They sometimes overlap.
- **Nothing of ours was running at the hang.** In the hang, `OnIdle` stopped being called (the UI thread froze) while no script callback was running. In the last log, the MIDI thread still delivered and completed a button press 5 s after the UI thread froze.
- **Generic-controller test:** with the MK2 on FL's generic controller (no script), recording didn't hang. The generic controller never ran the minimize/refocus steps, though, so this doesn't clear or convict the script.
- **Cause unconfirmed.** It could be FL 2026 itself, or an interaction between FL 2026 and MIDI scripts (the Fire and FLkey vendor scripts were running too).

**Status.** **Use FL Studio 2025.** The debug log is off (`ENABLED = False` in [diagnostics.py](flc_maschine/diagnostics.py)).

**Script changes made during the investigation (kept, they're sound in any version)**
- FL state is read, and LEDs are written, only from `OnIdle`. `OnMidiMsg` and `OnRefresh` just mark the controller dirty, because FL runs them on different threads at the same time.
- Pad presses use the last render's snapshot (for FPC), rather than querying FL from the MIDI thread.
- Pad aftertouch never triggers a render.
- No FL reads while `general.safeToEdit()` is false; the render waits for `OnIdle`.
- The debug log itself: [diagnostics.py](flc_maschine/diagnostics.py). Never use `gc.get_objects()` in it: in FL's embedded Python it fails with `SystemError: ... returned NULL without setting an exception`.

**Re-investigating** (e.g. after an FL 2026 update)
1. Set `ENABLED = True` in `flc_maschine/diagnostics.py` and reload the script.
2. Reproduce: record some notes, switch to another window, come back.
3. Copy `flc_debug.log` (in this folder) before reopening FL; it restarts when the script loads.
4. Isolate: repeat with only the MK2 script (Fire and FLkey set to no script), then with only the Fire and FLkey scripts.
5. Windows keeps the hang report under `C:\ProgramData\Microsoft\Windows\WER\ReportArchive` (`AppHang_FL64.exe_…`).

**Reading the debug log**
- `> OnMidiMsg [t1234]` … `< OnMidiMsg` bracket each callback, with the id of the thread FL called it on. `OnIdle` is only counted. A `>` with no `<` at the end of the file is what was running when FL died.
- `midi <CONTROL> <kind> <value>` is each decoded control message (aftertouch is only counted), and `refresh flags 0x…` is each refresh.
- `render skipped: FL not safe to edit` / `FL safe again` mark FL's busy periods. `slow <callback>: N ms` flags callbacks over 25 ms, and `! exception in …` gives a traceback.
- A `stats:` line every 5 s (from `OnIdle`) gives call counts, renders and the slowest render, and state sizes. Because it is the only line written while idle, **any** hang during an idle period leaves a log ending on a stats line. The first missing stats line dates the freeze of the UI thread.
- Optional, off by default: `MEMORY_STATS` (a `memory:` line with allocated blocks and GC counters) and `WATCH_GC` (`gc start/stop gen2` lines).

## Transpose: channel pitch units and maximum range unconfirmed

**Observed:** 2026-09-28, while moving shift Pads 13–16 (Semitone/Octave −/+) onto the selected channel's pitch.

**Units.** The manual says `channels.getChannelPitch(index, 1)` and `setChannelPitch(index, value, 1)` work in semitones. Arturia's KeyLab mk3 script uses unit 1 as cents (range × 100). Both agree that mode 2 is the pitch range in semitones. The script avoids unit 1: it reads the normalised pitch (mode 0, −1…+1 of the range) and the range (mode 2), and sets the normalised pitch ([pads.transpose](flc_maschine/handlers/pads.py)).

**Maximum range.** When a step goes past the channel's pitch range (FL's default is ±2 semitones), the script widens the range to 12, 24, 36 or 48 semitones, and stops the pitch at ±48 (`MAX_PITCH_RANGE`). That 48 is a guess at FL's maximum range. If FL caps the range lower, the knob will stop short of the hint's value. Lower `PITCH_RANGE_STEPS` to match.

**Checking in FL Studio.** Select a channel and turn shift mode on (F8). Pad 13 should move the channel's pitch knob to +100 cents. Pad 16 should set the range in the channel's settings to 12 and the knob to +13 semitones. Keep pressing Pad 16 up to +48 and compare the knob with the hint.
