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

**Candidate script-side mitigation (not implemented).** This script reads more FL state on every refresh than the old one, and refreshes fire while the dialog is open. The extra reads are the selected channel's colour, `plugins.isValid` and `plugins.getPluginName`, and FPC pad data. FL can be unsafe to query while a modal dialog is open. Novation's FLkey script checks `general.safeToEdit()` and suspends its reads and input while it returns false, refreshing everything afterwards. Doing the same in `MaschineMk2.render` may let the dialog open safely. Test it by clearing the default recording option again.

## FL Studio 2026: `transport.getSongPos` doesn't follow the playhead in Song mode (worked around)

**Observed:** 2026-09-28, FL Studio 2026, while building Step Left / Right on the Maschine MK2.

**Symptom.** Stopped in Song mode, `transport.getSongPos()` returns 0 in every mode (ms, seconds, absolute ticks, bars, steps, ticks). `transport.getSongPosHint()` stays at `1:01:00`. This holds even after `transport.setSongPos()` or a mouse click has moved the playhead. Step Right therefore moved one step once and then kept asking for the same position. Pattern mode reads the position correctly, though sometimes a press late.

**Workaround in the script.** Step Left / Right read the position with `mixer.getSongTickPos()`, which follows the playhead in both Song and Pattern mode, in the same absolute ticks `transport.setSongPos(…, SONGLENGTH_ABSTICKS)` takes ([transport_controls.py](flc_maschine/handlers/transport_controls.py)). `arrangement.currentTime()` also follows it in Song mode.

**Related setup.** Step sizes come from FL's main snap (the toolbar snap, `ui.getSnapMode()`). The Playlist and Piano Roll have their own snap settings, which the API doesn't report. Set them to "Main", or FL may round the playhead to a different grid than the one the script steps by.
