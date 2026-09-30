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

**Checking in FL Studio.** Select a channel and turn shift mode on (F3). Pad 13 should move the channel's pitch knob to +100 cents. Pad 16 should set the range in the channel's settings to 12 and the knob to +13 semitones. Keep pressing Pad 16 up to +48 and compare the knob with the hint.

## MK2 bridge: a feedback loop through loopMIDI makes the MK2 run wild (guarded)

**Observed:** 2026-09-29, with the Bridge controller type, after restarting.
- One pad hit set off a continuous stream of MIDI, and the volume maxed out.
- Stop didn't work.
- FL flipped between song and pattern mode in a rapid loop.

**Cause (diagnosed from the symptoms):** FL was receiving the script's own output as input.
- **How it gets back in:** every loopMIDI port appears in both FL's Input and Output lists. `MK2 Bridge Out` enabled as an Input, or `MK2 Bridge In` given the script's port number in Outputs (FL sends the script's output to every output with that number), routes it back in.
- **Why it runs away:** the script's LED messages look like MK2 presses.
  - **Button lights:** an echoed Scene LED is a Scene press, which toggles song mode and changes the LED, which is sent again.
  - **Pads:** every press makes the script resend that control's LED, so an echoed pad press repeats forever.
  - **Volume:** the Volume button's message is CC 7, MIDI channel volume.
  - **Colours:** the pad and group colour messages on channels 2 and 3 used to be passed to FL as notes and CCs.
- **Not the cause:** restart handling. FL restarting resends all LEDs and the full bridge state, and the bridge restarting sends a hello that does the same.

**Guard (implemented):** [feedback.py](flc_maschine/feedback.py).
- **What trips it:** an input on channels 2 or 3, the script's own channel-16 messages coming back, or a burst of inputs matching button-LED messages just sent.
- **What happens then:** the script stops sending and ignores input until it's reloaded, and says so in the hint bar and Script output.
- **Unrecognised messages** are no longer passed to FL.

**Fix the settings:** Inputs: only `MK2 Bridge In` enabled. Outputs: only `MK2 Bridge Out` has the script's port number. Then reload the script.

## MK2 bridge: MIDI input overflow when recording starts, and a false feedback trip (fixed)

**Observed:** 2026-09-29, pressing Play with Record on while testing Note Repeat. FL reported a MIDI input overflow, and the script stopped with "MK2: FL is receiving its own output…". Before that, Script output showed `unmapped midi id 176 chan 0 data1 123 data2 0`. The routing was correct, so this was no feedback loop.

**What happened:**
1. **The input overflowed.** FL's MIDI input overflowed while FL was busy starting to record. The likely cause is the dense pad pressure (poly aftertouch) stream from held pads, which the bridge passed through message for message.
2. **FL cleared hanging notes.** It sent CC 123 (All Notes Off) on all 16 channels through the script's input.
3. **The guard tripped falsely.** The copy on channel 2 tripped the feedback guard, whose "channels 2/3 are echoes" rule didn't allow for channel-mode messages. The script never sends CC 120–127.

**Fixes:**
- **Guard:** channel-mode CCs (120–127) are never echoes, and the controller swallows them quietly ([feedback.py](flc_maschine/feedback.py)). A trip now logs the message that caused it.
- **Bridge, pressure:** it thins pad pressure, dropping repeated values and sending at most one per pad every 10 ms, always the latest.
- **Bridge, traffic warning:** it logs any second with more than 400 messages to FL, e.g. "heavy MIDI to FL: 612 msg/s (pad pressure 580)".

**If an overflow happens again:** check the bridge console for the traffic line, to see what was flooding.

## MK2 bridge: a large audio buffer makes Note Repeat jitter (smoothed in the bridge)

**Observed:** 2026-09-29, recording Note Repeat while FL was playing, with FL's ASIO driver at a 512-sample buffer. Every repeat was slightly early or late, never drifting further, so quantizing to 1/6 or 1/4 step lined everything up. At 256 samples the jitter was gone.

**Cause (most likely):** FL processes MIDI once per audio buffer, not continuously.
- **Outgoing clock:** it sends its MIDI clock (Send master sync) in steps of one buffer. The bridge plays a repeat when a clock tick arrives, so the repeat inherits that step.
- **Recording:** incoming MIDI is probably also placed in steps of one buffer, adding the same kind of error on the way back in.
- **The size of the error** is up to about one buffer's length:

  | Buffer | At 48 kHz | At 96 kHz |
  |---|---|---|
  | 512 | ~10.7 ms, noticeable | ~5.3 ms |
  | 256 | ~5.3 ms, fine in testing | ~2.7 ms |
  | 128 | ~2.7 ms | ~1.3 ms |

The bridge adds only about 1 ms of its own (loopMIDI and its 1 ms timer). This is also why FL warns that master sync with ASIO may be inconsistent.

**Workaround before the fix, still useful for latency:** set FL's audio buffer to **256 samples or less** (Options > Audio settings).
- **FL Studio ASIO's minimum** here is 256.
- **A dedicated audio interface** with its own ASIO driver (e.g. NI Komplete Audio) typically goes lower, to 64 or 32 samples; the exact minimum depends on the model and driver.
- **A higher sample rate** also shortens each buffer: 256 samples at 96 kHz is ~2.7 ms.
- **The trade-off** is CPU: smaller buffers (or higher rates) can make heavy projects crackle.

**Symptom to recognise:** repeats that are a little early or late, never getting worse, and that line up after quantizing to a small division. If instead they drift further off over time, or sit a constant amount off a triplet grid, it's something else.

**Fix in the bridge (2026-09-29):** it no longer plays a repeat when each tick arrives. It smooths FL's clock with a delay-locked loop, estimating tempo and beat position from many ticks, and plays repeats on its own 1 ms timer. In a simulation of 512-sample clumps, repeats are within 1 ms of even, against about 8 ms firing on the raw ticks. Start the bridge with `--timing` to see FL's real tick jitter and the smoothed figure.

**What remains:**
- **Recording error:** any error FL adds when it records the incoming notes, if it places incoming MIDI in whole-buffer steps. Smaller buffers still help with that, and with latency.
- **A constant offset:** a few ms, the same for every note. FL's clock is always a little late, and the model follows its average.

**Confirmed in FL (2026-09-29):** at the default 512-sample buffer and 140 BPM, `--timing` showed raw tick jitter of about ±7 ms, smoothed to ±0.3–0.4 ms. Note Repeat worked well without lowering the buffer.
