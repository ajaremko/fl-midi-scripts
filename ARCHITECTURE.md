# FL Complete Architecture

This document describes how the scripts in this repo are built: where each concern lives, how a MIDI message becomes an action and an LED update, and how to extend the code. [README.md](README.md) is the functional spec (what every control should do). The format of the Controller Editor templates is documented in `NI Maschine MK2/controller-editor-templates.md` in the older MK2 repo, the sibling folder of this one.

Only the Maschine MK2 script exists so far. The Akai Fire and FLkey 2 scripts will follow the same shape.

## Contents

1. [Repository layout](#1-repository-layout)
2. [Runtime model](#2-runtime-model)
3. [Data flow](#3-data-flow)
4. [Modules](#4-modules)
5. [Design rules](#5-design-rules)
6. [Coupling to the Controller Editor template](#6-coupling-to-the-controller-editor-template)
7. [Extending the script](#7-extending-the-script)
8. [Testing](#8-testing)
9. [Porting from the old MK2 script](#9-porting-from-the-old-mk2-script)

---

## 1. Repository layout

```text
FL Complete/
├── device_FLC_MaschineMK2_Hardware.py  entry script for the MK2's own ports: MaschineMk2(bridge=False)
├── device_FLC_MaschineMK2_Bridge.py    entry script for the MK2 bridge's ports: MaschineMk2(bridge=True), adds Note Repeat
├── mk2_bridge/                    helper program run beside FL (not by FL): MK2 <-> loopMIDI, times Note Repeat
│   ├── bridge.py                  Bridge (routing, lock), NoteRepeater (repeat logic), find_port, main (ports, timer thread)
│   ├── requirements.txt           mido, python-rtmidi
│   └── start_bridge.bat           starts it in a console window
├── flc_maschine/                  the MK2 script's package
│   ├── controls.py                hardware config: every control and the MIDI message it sends
│   ├── bindings.py                function config: which handler each control runs, per layer
│   ├── state.py                   ControllerState, shared by handlers and the renderer
│   ├── notes.py                   which note each pad plays in each pad group
│   ├── fpc.py                     reads the selected FPC's pads: note, colour, empty
│   ├── events.py                  raw FL event -> ControlEvent
│   ├── dispatcher.py              ControlEvent -> handler
│   ├── controller.py              MaschineMk2: wires the pieces together
│   ├── macros.py                  macro mappings for E9–E16, per plugin and channel type
│   ├── bridge_link.py             bridge mode: sends Note Repeat state to the MK2 bridge (channel 16)
│   ├── log.py                     prefixed printing to the Script output window
│   ├── feedback.py                FeedbackGuard: stops a MIDI feedback loop (own output coming back in)
│   ├── diagnostics.py             crash log (flc_debug.log): callbacks, stats, exceptions
│   ├── handlers/
│   │   ├── common.py              unimplemented, passthrough, on_press
│   │   ├── channel_controls.py    Solo / Mute on the selected channel; Shift + Select opens its Piano Roll
│   │   ├── channel_colors.py      Color mode (F12): PALETTE and pick, colouring the selected channels
│   │   ├── macro_knobs.py         E9–E16: macros for the focused plugin (mappings in macros.py)
│   │   ├── presets.py             F13/F14: previous/next preset of the selected channel's plugin
│   │   ├── mixer_tracks.py        F16: route the selected channels to empty mixer tracks (FL's Ctrl+L)
│   │   ├── channel_knobs.py       E1–E8: the selected channel's volume, pan, pitch, pitch range, gate, shift, swing, mixer track
│   │   ├── edit.py                undo, redo, compare, quantize (shift-mode pads)
│   │   ├── encoder.py             master encoder: navigate/push the focused window; Volume/Swing/Tempo overrides
│   │   ├── groups.py              select (Group A–H)
│   │   ├── transport_controls.py  Restart, Play/Metro, Rec/Count-In, Step Left/Right
│   │   ├── ui_commands.py         send: one FL command per press (F1 Menu, F2/F10 Esc, F9 Alt Menu, shift Pads 7/8 tempo nudge)
│   │   ├── windows.py             toggle (BROWSE, F5–F8)
│   │   ├── selection.py           push-and-turn drag selection (Channel Rack channels, mixer tracks)
│   │   ├── pads.py                play: translate pad notes for the selected group
│   │   ├── pad_modes.py           the Pad Mode override: step and show the pad mode (Default, Keyboard, Sequencer)
│   │   ├── modes.py               toggle (Shift / New), once (one-shot mode functions)
│   │   ├── note_repeat.py         toggle (Note Repeat, bridge mode only)
│   │   └── pattern_controls.py    new_pattern, duplicate_pattern
│   └── rendering/
│       ├── fl_state.py            FlSnapshot: the FL Studio state the renderer needs
│       ├── colors.py              HSB colour values and FL colour conversion
│       ├── renderer.py            state + snapshot -> LED frame
│       └── output.py              LedWriter: frame -> MIDI, only what changed
├── tests/
│   ├── fl_stubs/                  stand-ins for FL Studio's device, midi, ui, transport, channels and plugins modules
│   ├── test_template.py           controls.py matches the .ncm2 template
│   └── test_scaffold.py           end-to-end tests through the entry script
├── NI Maschine MK2/
│   └── FL Complete.ncm2           Controller Editor template loaded on the MK2
├── Akai Fire/                     (future)
└── Novation FLKeys 2/             (future)
```

- **Entry scripts sit at the repo root.** FL Studio only looks for `device_*.py` one folder below `Settings/Hardware`, and this repo is that folder. Each controller gets its own entry script here.
- **One package per controller.** The package name is distinct (`flc_maschine`, not `maschine_mk2`) so it cannot collide with the older MK2 script's package if both are installed.
- **Templates live in per-device folders.** Folder names with spaces cannot be Python packages, so they never clash with code.

## 2. Runtime model

- **One instance per port.** FL Studio runs a separate copy of the script for each MIDI port it is assigned to. Each copy has its own module namespace, so module-level state is never shared with the other controllers' scripts. The controllers only share FL Studio's own state: focus, selection, transport.
- **Two thin entry scripts.** [device_FLC_MaschineMK2_Hardware.py](device_FLC_MaschineMK2_Hardware.py) ("FL Complete Maschine MK2 (Hardware)") is for the MK2's own ports. [device_FLC_MaschineMK2_Bridge.py](device_FLC_MaschineMK2_Bridge.py) ("… (Bridge)") is for the MK2 bridge's loopMIDI ports. Each creates one `MaschineMk2(bridge=False/True)` and forwards `OnInit`, `OnDeInit`, `OnMidiMsg`, `OnRefresh` and `OnIdle` to it. The `# name=` header must stay on line 1; it is FL's Controller type name.
- **Bridge mode.** With `bridge=True`, the controller adds what needs the bridge:
  - the `bindings.BRIDGE_BASE` overlay (Note Repeat)
  - a [bridge_link.py](flc_maschine/bridge_link.py) `BridgeLink` that sends the bridge its state
  - an answer to the bridge's hello

  With `bridge=False` none of this exists: Note Repeat stays an `unimplemented()` placeholder, and nothing is sent on channel 16.
- **The MK2 bridge.** [mk2_bridge/bridge.py](mk2_bridge/bridge.py) is an ordinary Python 3 program on the Windows host, not run by FL.
  - **Ports:** it owns the MK2's ports and passes MIDI to FL through two loopMIDI ports: "MK2 Bridge In" for FL's input, "MK2 Bridge Out" for its output.
  - **Timing:** it times Note Repeat with FL's MIDI clock (master sync) while FL is playing, and with its own 1 ms timer thread while stopped. FL's `OnIdle` was far too irregular for this.
  - **Clock smoothing:** FL sends its clock once per audio buffer, so ticks arrive in clumps, up to a buffer late: about 10 ms at 512 samples. Ticks don't play anything. `clock()` corrects a delay-locked loop, a model of when ticks should arrive: `anchor_pos`, `anchor_time`, and `spc` seconds per tick, with the phase gain `ALPHA_LOCK` for the first beat and `ALPHA` after, and a tempo gain of `ALPHA² / 4`.
    - **Stepping:** the timer thread's `tick()` advances a virtual position along the model and runs `_step()` (the per-tick logic: grid lines, first notes, gates) for each position crossed.
    - **Running ahead:** the model may run `MAX_AHEAD` ticks past the last tick received, so a late tick doesn't delay its grid line.
    - **Tempo:** a tempo message from the script resets `spc` at once.
    - **Jumps:** song-position jumps re-anchor continuously in time, unless the next tick is more than half a tick off, as with an extra tick at the loop point; then the model snaps to it.
    - **`--timing`:** every 5 s, logs the raw tick jitter and the smoothed correction (`_TimingStats`).
  - **Pad pressure thinning:** the MK2 sends pad pressure (poly aftertouch) densely, and a burst while FL is busy overflowed FL's MIDI input. The bridge drops repeated values and sends at most one per pad every `PRESSURE_INTERVAL` (10 ms), the latest following on the timer thread. A 0 goes at once, and a release drops pending pressure. Traffic to FL is counted, and a second over `FLOOD_WARN` messages is logged (at most once a minute).
  - **First note on the grid:** while the clock runs, a press within the grace window after the latest grid line (`GRACE_FRACTION` of an interval, at most `GRACE_MAX`) plays at once and counts as that line. Any other press is held back (`pending_first`) and played by the next grid-line clock. A pad released before then (a quick tap) still plays that one note with its gate, and its release isn't passed on. If the clock stops first, the timer plays the held note at once.
  - **No double hits:** a pad never sounds twice within `MIN_SPACING` (half an interval) or twice at the same clock position. FL's loop wrap otherwise hits twice at the downbeat: the clock at the end of the bar and song position 0 are both grid lines, milliseconds apart.
  - **Rate changes:** on the clock, the next grid line of the new rate plays, spacing permitting. On the timer, the new interval counts from the pad's last hit.
  - **Replaying:** a repeat replays the pad's raw note-on and note-off, so the script handles each one as an ordinary pad hit (groups, FPC, fixed velocity).
  - **Threads:** `NoteRepeater` is pure logic. `Bridge` calls it under one lock from three threads: the MK2's input, FL's output and the timer.
  - **Setup** is in the README.
- **Script-to-bridge messages** are control changes on MIDI channel 16, which the MK2 template never uses. The bridge keeps them out of the MK2's LED stream. The numbers are defined in both [bridge_link.py](flc_maschine/bridge_link.py) and [bridge.py](mk2_bridge/bridge.py) and must match:

  | CC | Direction | Meaning |
  |---|---|---|
  | 1 | script → bridge | Note Repeat: 0 off, 127 on |
  | 2, 34 | script → bridge | Rate in MIDI clocks (24 per beat), MSB then LSB; applied on the LSB. Note Repeat's own rate (`note_repeat.RATES`), independent of FL's snap. Triplets are just other clock counts, so the bridge knows nothing of the modes. |
  | 3, 35 | script → bridge | Tempo × 10, MSB then LSB; used while FL is stopped |
  | 4 | script → bridge | FL playing: 0 stopped, 127 playing |
  | 5 | script → bridge | Pads play notes: 127 with no mode on, 0 in Shift, New or Color mode; while 0 the bridge passes pads straight through, never holding back or repeating them, and it releases repeating pads when it turns 0 |
  | 126 | bridge → script | FL is playing but no MIDI clock arrives (Send master sync off): the script shows a hint once |
  | 127 | bridge → script | Hello: the bridge (re)started; the script resends everything |

  `BridgeLink.write` runs from the render (`OnIdle`) and sends only values that changed. While Note Repeat is on, the controller renders at least every `BRIDGE_RECHECK_IDLES` idles, so tempo changes that FL doesn't report with a refresh still reach the bridge. The feedback guard expects CC 126 and 127 from the bridge; any other channel-16 input is the script's own output coming back.
- **Embedded Python.** FL Studio's Python may not have the full standard library. Use only modules the shipped vendor scripts already use (`enum`, `typing`, `time`, `math`, `traceback`). Avoid `dataclasses`; the code uses plain classes with `__slots__` instead.

## 3. Data flow

One button press, from the hardware and back to its LEDs:

```text
 FL Studio                    flc_maschine
─────────────────────────────────────────────────────────────────────────────────────
 OnMidiMsg(event) ──▶ MaschineMk2.on_midi_msg
                        │
                        ▼
                      events.decode(event) ── looks up controls.BY_KEY
                        │                     no match ──▶ log "unmapped midi", FL handles it
                        │ ControlEvent
                        ▼
                      controller.invalidated.add(control id)   (presses and releases only)
                        │
                        ▼
                      dispatcher.dispatch ── bindings.lookup(state, control id)
                        │                     walks state.active_layers()
                        │                     no binding ──▶ log "no binding", FL handles it
                        ▼
                      handler(controller, ev) ──▶ changes ControllerState and/or calls FL Studio
                        │
                        ▼
                      controller.dirty = True               (not for aftertouch)

 OnRefresh(flags) ──▶ controller.dirty = True

 OnIdle() ─────────▶ dirty and general.safeToEdit()?  no ──▶ try again next idle
                        │ yes
                        ▼
                      MaschineMk2.render: FlSnapshot.read() ──▶ controller.fl
                        │
                        ▼
                      renderer.render(state, fl) ──▶ frame {control id: value}
                        │
                        ▼
                      LedWriter.write(frame) ── diff against last sent ──▶ device.midiOutMsg ──▶ MK2
```

1. **Decode.** [events.decode](flc_maschine/events.py) finds the control by (message type, channel, number) and turns the raw message into a `ControlEvent` using the control's template mode (see [section 6](#6-coupling-to-the-controller-editor-template)).
2. **Invalidate.** Some buttons light themselves when pressed. After a press or release, the controller notes the control, and the next render resends the state the script wants for it.
3. **Dispatch.** [dispatcher.dispatch](flc_maschine/dispatcher.py) finds the handler in the highest-priority active layer, marks the event handled and calls it inside `try/except`.
4. **Handle.** The handler changes `ControllerState`, calls FL Studio, or hands the message back to FL with `ev.pass_to_fl()`. Handlers that need FL state they would otherwise query use `controller.fl`, the last render's snapshot (the pads do this for FPC).
5. **Mark dirty.** `OnMidiMsg` and `OnRefresh` only set `controller.dirty`. **They never read FL state or write LEDs**: the crash logs showed FL running them at the same time on different threads (see [known-issues.md](known-issues.md)).
6. **Render, from `OnIdle` only.** When dirty and FL is safe to edit, the controller reads an `FlSnapshot` of FL Studio (kept as `controller.fl`) and lets [pads.follow_fpc_selection](flc_maschine/handlers/pads.py) react to it (jumping to Group E when an FPC is newly selected). Then [renderer.render](flc_maschine/rendering/renderer.py) builds a frame from the state and the snapshot. Any number of events between two idles cause one render.
7. **Output.** [LedWriter.write](flc_maschine/rendering/output.py) sends only the LEDs whose value differs from what it last sent.

The other callbacks:

| Callback | What happens |
|---|---|
| `OnInit` | Log the port, forget every cached LED value, render. The first frame turns off every LED except those the rules light. |
| `OnRefresh` | Mark dirty. FL calls it when its state changes, including window focus; the next `OnIdle` renders. |
| `OnIdle` | Send queued menu commands once their menu is open (`ui_commands.run_menu_commands`), and show a pending preset name (`presets.show_preset_name`). If dirty and `general.safeToEdit()` allows it, resend invalidated LEDs and render; while FL is busy (dialogs, the plugin picker, channels being added) it stays dirty and retries. Then `diagnostics.tick` writes its stats line. Also the hook for future timed features such as long presses or blinking. |
| `OnDeInit` | Write an empty frame, which turns every LED off. |

## 4. Modules

| File | Responsibility | Key names | Uses FL modules |
|---|---|---|---|
| [controls.py](flc_maschine/controls.py) | Every control, its README label and the MIDI message the template makes it send. The only place MIDI numbers appear. | `Control`, `ALL_CONTROLS`, `BY_ID`, `BY_KEY`, `LED_CONTROLS`, `PADS` | No |
| [bindings.py](flc_maschine/bindings.py) | Which handler runs for each control in each layer: base, the global modes (Shift, New, Color) and the pad modes (Default binds nothing; Keyboard and Sequencer bind the pads to placeholders for now). `pads_play_notes(state)` tells the bridge whether the pads are notes: no global mode on and every pad resolving to `pads.play` | `LAYERS`, `MODE_CONTROLS`, `lookup`, `pads_play_notes` | `midi` constants |
| [state.py](flc_maschine/state.py) | Mutable controller state | `ControllerState`, `active_layers`, `BASE`, `SHIFT`, `NEW`, `COLOR`, `DEFAULT_PADS`, `KEYBOARD`, `SEQUENCER`, `PAD_MODES` | No |
| [notes.py](flc_maschine/notes.py) | Which note each pad plays: 16 notes per group, Group A from 0; which notes are black keys and Cs (Keyboard pad mode's lights); which FPC bank and pad each group and pad maps to | `pad_note`, `is_black_key`, `is_c`, `BLACK_KEYS`, `PAD_INDEX`, `NOTES_PER_GROUP`, `FPC_BANK_FOR_GROUP`, `fpc_pad` | No |
| [fpc.py](flc_maschine/fpc.py) | Detect a selected FPC and read its pads | `selected_fpc_channel`, `read_pad`, `read_banks`, `FpcPad` | `channels`, `midi`, `plugins` (reads only) |
| [events.py](flc_maschine/events.py) | Decode raw MIDI into control events | `ControlEvent`, `decode`, `PRESS`, `RELEASE`, `TURN`, `VALUE`, `PRESSURE` | `midi` constants |
| [dispatcher.py](flc_maschine/dispatcher.py) | Route an event to its handler; release and aftertouch follow the press; fault isolation | `dispatch` | No |
| [controller.py](flc_maschine/controller.py) | Owns the state and the LED writer; implements the FL callbacks. `MaschineMk2(bridge)` selects hardware or bridge mode; in bridge mode it also owns a `BridgeLink`, answers the bridge's hello, and turns Note Repeat off in the bridge on deinit | `MaschineMk2`, `BRIDGE_RECHECK_IDLES` | `device` |
| [bridge_link.py](flc_maschine/bridge_link.py) | Bridge mode: sends the MK2 bridge the Note Repeat state (on/off, its rate in MIDI clocks, tempo, FL playing) as channel-16 CCs, only when they change, plus whether the pads play notes (`bindings.pads_play_notes`); recognises the bridge's hello and no-clock warning | `BridgeLink`, `rate_clocks`, `is_hello`, the `CC_*` numbers | `device`, `midi` |
| [feedback.py](flc_maschine/feedback.py) | Notices the script's own output coming back as input (a MIDI settings mistake, easy with loopMIDI ports) and trips. Sure signs: any note, aftertouch or CC on channels 2 or 3, which only the HSB colour messages use (except channel-mode CCs 120–127, which the script never sends but FL does, on every channel, e.g. All Notes Off after an input overflow; the controller swallows those quietly); any channel-16 message other than the hello in bridge mode. Otherwise, repeated look-alikes: `ECHO_LIMIT` inputs within `ECHO_PERIOD`, each matching a mono LED message sent in the last `ECHO_WINDOW`. Once tripped, the controller swallows all input and sends nothing until the script is reloaded | `FeedbackGuard`, `WARNING`, `ECHO_*`, `clock` | `midi` |
| [log.py](flc_maschine/log.py) | `[FLC MK2]` prefixed output; optional raw MIDI trace | `info`, `trace_midi`, `TRACE_MIDI` | No |
| [diagnostics.py](flc_maschine/diagnostics.py) | **Off by default (`ENABLED = False`).** Crash log that survives FL crashing: writes `flc_debug.log` (next to the entry script) a line at a time. The entry script runs every callback through `run` (counted, timed, `> name [t<thread id>]` and `< name` lines except for `OnIdle`, exceptions logged and re-raised); `tick` writes a stats line every 5 s (call counts, renders, state sizes). Memory counters (`MEMORY_STATS`) and full-GC logging (`WATCH_GC`) are optional and off by default: they were ruled out as useful, and are suspected of contributing to crashes. Never use `gc.get_objects()` here: it fails in FL's Python. Switch off with `ENABLED = False` | `run`, `note`, `count`, `tick`, `start`, `ENABLED`, `LOG_FILE` | `general` (version only) |
| [handlers/common.py](flc_maschine/handlers/common.py) | Reusable handlers and wrappers. `unimplemented(...)` handlers carry `placeholder = True`, so modes don't highlight them | `unimplemented`, `passthrough`, `on_press` | No |
| [handlers/edit.py](flc_maschine/handlers/edit.py) | Editing actions for the shift-mode pads: Pad 1 Undo (`general.undoUp`), Pad 2 Redo (`general.undoDown`), Pad 3 Compare (`general.undo`, FL's Ctrl+Z, which toggles the last edit in FL's default undo mode) and Pad 5 Quantize (`channels.quickQuantize` on the selected channel; FL offers no quantize strength, so Pad 6 Quantize 50% can't exist) | `undo`, `redo`, `compare`, `quantize` | `general`, `channels` |
| [handlers/note_repeat.py](flc_maschine/handlers/note_repeat.py) | Note Repeat (bridge mode only, through `bindings.BRIDGE_BASE`). `toggle` cycles `state.note_repeat` through `OFF` → `ON` → `TRIPLETS`. `RATES` holds four divisions per mode (straight 1/4…1/32, triplet 1/4T…1/32T, in MIDI clocks), so straight and triplet grids never mix; one division index is shared, so switching modes keeps the division. `step_rate` moves within the mode, called by `encoder.turn` first thing while Note Repeat is on. Both show the mode and rate in the hint bar. The bridge does the repeating | `toggle`, `step_rate`, `OFF`, `ON`, `TRIPLETS`, `RATES`, `rate_name`, `rate_clocks` | `ui` |
| [handlers/channel_colors.py](flc_maschine/handlers/channel_colors.py) | Color mode (F12): `PALETTE`, 16 `0xRRGGBB` hues (written out; `colorsys` may not be in FL's Python), and `pick(i)`, the Color layer's pad handlers, which set `PALETTE[i]` on every selected channel (`channels.isChannelSelected`, `setChannelColor`). The renderer's `_color_mode_pads` lights the pads in the palette, the selected channel's current colour at full brightness and the rest at `PALETTE_DIM` | `PALETTE`, `pick` | `channels`, `ui` |
| [handlers/modes.py](flc_maschine/handlers/modes.py) | Handlers that change the controller's own modes: `toggle(mode)` for F3 and F11 (Shift), F4 (New) and F12 (Color) (entering a mode also clears `encoder_mode`), and `once(handler)`, which turns the mode off after a New-mode function runs | `toggle`, `once` | No |
| [handlers/macro_knobs.py](flc_maschine/handlers/macro_knobs.py) | E9–E16, macros. The target: a focused mixer effect (`mixer.getActiveEffectIndex`), else the selected channel's plugin, else a Sampler / Audio Clip / Layer channel (`channels.getChannelType`), else none. Plugin macros look up the named parameter once per plugin (`getParamCount` / `getParamName`, ignoring case and spaces). They step it by `MACRO_STEP` with `plugins.setParamValue(..., PIM_None)`, keeping a running value so stepped parameters move and restarting from the plugin's value if it changed elsewhere, and write the current value first (FL ignores a first write). The hint is `name: value string`. Channel macros step a REC event as E1–E7 do. A plugin without macros gets a hint, and its parameter list is logged once per session | `turn`, `MACRO_STEP`, `CHANNEL_TYPES` | `plugins`, `mixer`, `channels`, `general`, `midi`, `ui` |
| [macros.py](flc_maschine/macros.py) | Macro mappings: `MACROS` (plugin name → up to 8 parameter names, or parameter numbers where names repeat or follow the preset, as for FLEX) and `CHANNEL_MACROS` (Sampler / Audio Clip / Layer → up to 8 `REC_Chan_` offsets). Our own choices; an empty list means none yet | `MACROS`, `CHANNEL_MACROS` | No |
| [handlers/channel_knobs.py](flc_maschine/handlers/channel_knobs.py) | E1–E8, the selected channel's own settings. E1–E3 and E5–E7 step a channel REC event (`channels.getRecEventId(ch) + REC_Chan_Vol / Pan / Pitch / GateTime / TimeOfs / SwingMix`) with `channels.incEventValue(id, delta, EKRes × scale)` and write it with `general.processRECEvent(..., REC_UpdateValue | REC_UpdateControl | REC_ShowHint)`, so FL moves its knob and shows the value in the hint bar. E4 sets the pitch range with `channels.setChannelPitch(ch, semitones, 2)`, one semitone per message, 1 to `pads.MAX_PITCH_RANGE` (the fine-tune REC event, `REC_Chan_OfsPitch`, didn't behave as a fine tune in FL). E8 steps `REC_Chan_FXTrack` one track per message, from Master (0) to the last insert (`mixer.trackCount() - 2`). `KNOBS` holds each knob's offset and step scale | `turn`, `pitch_range`, `mixer_track`, `KNOBS` | `channels`, `general`, `mixer`, `midi`, `ui` |
| [handlers/channel_controls.py](flc_maschine/handlers/channel_controls.py) | Solo and Mute: toggle solo (`channels.soloChannel`) or mute (`channels.muteChannel`) on the selected Channel Rack channel, whatever window is focused; nothing when no channel is selected. The renderer's `_channel_state` rule lights each button from the snapshot. Shift + Select (Events) runs `open_piano_roll`: `ui.openEventEditor(channels.getRecEventId(ch) + midi.REC_Chan_PianoRoll, midi.EE_PR)` for the selected channel | `solo`, `mute`, `open_piano_roll` | `channels`, `ui`, `midi` |
| [handlers/pattern_controls.py](flc_maschine/handlers/pattern_controls.py) | Pattern functions. New + Pattern jumps to the next empty pattern. Duplicate clones the current pattern with `patterns.clonePattern()`, first selecting it in the Picker if it isn't selected (`clonePattern` clones the selection; its index argument needs API 43) | `new_pattern`, `duplicate_pattern` | `patterns`, `midi` |
| [handlers/encoder.py](flc_maschine/handlers/encoder.py) | Master encoder. Turning navigates an open popup menu or the focused window (`NAVIGATION`); pushing does that window's action (`PUSH`; in the Channel Rack, `FPT_ItemMenu` opens the selected channel's right-click menu). Volume, Swing, Tempo, Navigate, Pattern, Grid and Pad Mode toggle an override mode that takes over turning to adjust master volume, swing or tempo, jog between open windows, patterns or main snap settings, or pick the pad mode (`MODES`, whose adjusters take `(state, delta)`). `toggle_mode(mode, hint)` runs `hint(state)` as the override turns on (Pad Mode shows the current pad mode). Push and turn: while the push is held (`state.push_held`), turning goes to `selection.drag` first, which selects in the Channel Rack or Mixer and takes priority over overrides and navigation; elsewhere the turn is handled as usual. The push's action (`_click`) runs on release, and only if the encoder didn't turn while held (`push_turned`). Encoder Push is in Gate mode in the template so the release arrives | `turn`, `push`, `toggle_mode`, `MODES`, `NAVIGATION`, `PUSH` | `mixer`, `transport`, `ui`, `midi` |
| [handlers/pad_modes.py](flc_maschine/handlers/pad_modes.py) | The Pad Mode override's turn: `step(state, delta)` moves `state.pad_mode` one mode per encoder message through `PAD_MODES`, stopping at the ends, and `show` hints "Pad mode: …", with "(not written yet)" for `NOT_WRITTEN` modes. Each pad mode's bindings are its layer in `bindings.LAYERS` | `step`, `show`, `NAMES`, `NOT_WRITTEN` | `ui` |
| [handlers/selection.py](flc_maschine/handlers/selection.py) | Push-and-turn drag selection. `TARGETS` holds, per window, where a range starts, how many items there are, and how to select one item exclusively or (de)select one: Channel Rack channels (`selectedChannel`, `channelCount`, `selectOneChannel`, `selectChannel`) and mixer tracks (`trackNumber`, `trackCount() - 1` to leave out the "Current" track, `setActiveTrack`, and `selectTrack`, which only toggles, guarded by `isTrackSelected`). `drag` starts the range at the anchor on the first turn and moves its end one item per encoder message, changing only the item that joins or leaves; it returns False with a popup menu open or neither window focused | `drag`, `TARGETS` | `channels`, `mixer`, `ui`, `midi` |
| [handlers/presets.py](flc_maschine/handlers/presets.py) | F13/F14: `step(-1/+1)` calls `plugins.prevPreset` / `nextPreset` on the selected channel's plugin, after checking there is a selection, a plugin (`plugins.isValid`) and presets (`getPresetCount`), each with a hint. The change is asynchronous: `getName(FPN_Preset)` can still read the old name or "" straight after. So the handler stores `(channel, old name, PRESET_WAIT_TICKS)` in `state.preset_hint`, and `show_preset_name`, called from `OnIdle`, shows "Preset: name" once the name changes, or after the wait | `step`, `show_preset_name`, `PRESET_WAIT_TICKS` | `plugins`, `channels`, `ui`, `midi` |
| [handlers/mixer_tracks.py](flc_maschine/handlers/mixer_tracks.py) | F16: FL's "Assign selected to free mixer track(s)" (Ctrl+L), which has no API call. `empty_tracks()` lists inserts 1 to `trackCount() - 2` (leaving out the "Current" track) with no channel routed to them, read across all groups (`getTargetFxTrack(i, True)` for `channelCount(1)` channels), no effect in any of `EFFECT_SLOTS` (`isTrackPluginValid`) and their default name ("Insert N" or ""). `assign_free_track` gives each selected channel the next one: it routes it with the `REC_Chan_FXTrack` REC event (as E8 does), copies the channel's name and colour (`setTrackName`, `setTrackColor`) and scrolls the Mixer to the first (`setTrackNumber(t, curfxScrollToMakeVisible)`) | `assign_free_track`, `empty_tracks` | `channels`, `mixer`, `general`, `ui`, `midi` |
| [handlers/groups.py](flc_maschine/handlers/groups.py) | Group A–H buttons: select the pad group | `select` | No |
| [handlers/transport_controls.py](flc_maschine/handlers/transport_controls.py) | Transport buttons. Step Left/Right move to the previous/next grid line of FL's main snap (`ui.getSnapMode`), sized from FL's timebase (`general.getRecPPQ`, `getRecPPB`). The position is read with `mixer.getSongTickPos()`, because `transport.getSongPos` stays at 0 in Song mode while stopped ([known-issues.md](known-issues.md)) | `restart`, `play`, `record`, `toggle_song_mode`, `metronome`, `count_in`, `step_left`, `step_right`, `snap_ticks`, `next_position` | `transport`, `general`, `mixer`, `ui`, `midi` |
| [handlers/ui_commands.py](flc_maschine/handlers/ui_commands.py) | Buttons that send one FL command per press. F1 Menu sends `FPT_Menu`, F9 Alt Menu `FPT_ItemMenu` (the item's context menu), F2 and F10 Esc `FPT_Escape`; Master Left and Right send `FPT_Left` and `FPT_Right`. Enter (`enter`) sends `FPT_Enter`, except in the Channel Rack with no popup menu open, where it opens the selected channel's plugin window (`channels.showCSForm(channel, 1)`, which opens a plugin's window or a sampler's channel settings; `showEditor` did nothing in FL 2025). `send` takes an optional value for jog commands: shift Pads 7/8 (Nudge Left/Right) send `FPT_TempoJog` −1/+1, a 0.1 BPM tempo step. `open_menu_then` opens a menu and queues follow-up commands, which `run_menu_commands` sends from `OnIdle` once FL reports the menu open (dropping them after `MENU_WAIT_TICKS`). New + Browse uses it to reach FL's Add menu: `FPT_Menu`, then `FPT_Right` ×3 ([known-issues.md](known-issues.md)) | `send`, `enter`, `open_menu_then`, `run_menu_commands` | `transport`, `ui`, `channels` |
| [handlers/windows.py](flc_maschine/handlers/windows.py) | BROWSE and F5–F8: show and focus a window, or hide it if already focused | `toggle` | `ui` |
| [handlers/pads.py](flc_maschine/handlers/pads.py) | Pads: rewrite the note to the selected group's note and pass it to FL (`_play`). `play` is Default pad mode, with FPC's banks on an FPC channel; `play_keyboard` is Keyboard pad mode, always chromatic. Both are marked `plays_notes`, which `bindings.pads_play_notes` checks. `follow_fpc_selection` (the Group E jump) only acts in Default pad mode. While fixed velocity (F15) is on, note-ons are also rewritten to velocity `FIXED_VELOCITY` (127). `transpose(semitones)` is shift Pads 13–16 (Semitone/Octave −/+): it moves the selected channel's pitch (FPC channels included), widening the channel's pitch range to the next of `PITCH_RANGE_STEPS` when needed, up to ±`MAX_PITCH_RANGE`, and shows the result in FL's hint bar | `play`, `play_keyboard`, `follow_fpc_selection`, `toggle_fixed_velocity`, `FIXED_VELOCITY`, `transpose`, `PITCH_RANGE_STEPS`, `MAX_PITCH_RANGE` | No |
| [rendering/fl_state.py](flc_maschine/rendering/fl_state.py) | Read FL Studio's state once per render: focused window, transport (playing, recording, song mode), selected channel's colour and solo/mute state, selected FPC and its pads, and for the bridge the tempo (normalised: some FL versions report BPM × 1000) | `FlSnapshot`, `WINDOWS` | `midi`, `ui`, `transport`, `channels`, and `plugins` through `fpc.py` (reads only) |
| [rendering/renderer.py](flc_maschine/rendering/renderer.py) | Decide every LED's value | `render`, `RULES`, `WINDOW_BUTTONS`, `MODE_BUTTONS`, `MODE_COLORS`, `LIT_BRIGHTNESS`, `DIM_BRIGHTNESS` | `midi` constants; no calls. Reads `bindings.MODE_CONTROLS` for `_mode_highlight`, which must stay the last rule |
| [rendering/colors.py](flc_maschine/rendering/colors.py) | HSB colour tuples; converts FL's `0xRRGGBB` colours | `rgb_to_hsb`, `with_brightness`, `OFF`, `WHITE`, `MAX` | No |
| [rendering/output.py](flc_maschine/rendering/output.py) | Send LED changes to the controller | `LedWriter` | `device`, `midi` |

Handler modules that perform FL actions, such as `handlers/windows.py`, import whichever FL modules they need.

### `Control`

| Field | Meaning |
|---|---|
| `id` | Stable name used everywhere else: `F5`, `PAD_1`, `GROUP_A`, `ENCODER` |
| `label`, `alt_label`, `area` | The README's Label, Alt Label and Area |
| `kind` | `BUTTON`, `ENCODER` or `PAD` |
| `msg`, `number`, `channel` | The MIDI message: `CC` or `NOTE`, its number, and the 0-based channel |
| `mode` | The template's behaviour: `TRIGGER`, `GATE` or `TOGGLE` for buttons and pads; `COMP` or `ABSOLUTE` for encoders |
| `led` | `MONO`, `HSB` (colour LED in HSB mode), or `None` for controls without an LED |
| `template_ref` | Where the control is in the `.ncm2` file; only the tests use it |

### `ControlEvent`

| Field | Meaning |
|---|---|
| `control` | The `Control` that sent the message |
| `kind` | `press`, `release`, `turn` (relative encoder), `value` (absolute encoder) or `pressure` (pad aftertouch) |
| `value` | The raw data byte: velocity, CC value or pressure |
| `delta` | For `turn`: signed steps, +1 clockwise and −1 counter-clockwise |
| `raw` | FL Studio's event, for anything else, including `handled` |

`is_press` and `is_release` are shortcuts, and `pass_to_fl()` sets `raw.handled = False`.

### `ControllerState`

| Field | Meaning |
|---|---|
| `mode` | The global mode: `SHIFT` (toggled by F3 or F11), `NEW` (toggled by F4, one-shot), `COLOR` (toggled by F12) or `None`. Only one is on at a time. Its layer takes priority over `base`, and only its button(s) (`renderer.MODE_BUTTONS`) and the controls in `bindings.MODE_CONTROLS[mode]` (bound to a real function, not a placeholder) are lit, RGB ones in their `renderer.MODE_COLORS` colour. |
| `held` | Control id → the handler that took its press, for gate controls currently held down |
| `encoder_mode` | The master encoder's override mode, `"VOLUME"`, `"SWING"`, `"TEMPO"`, `"NAVIGATE"`, `"PATTERN"`, `"GRID"` or `"PAD_MODE"`, toggled by those buttons; `None` when off. The active button is lit. Entering Shift or New mode clears it. |
| `push_held`, `push_turned` | The encoder push is held down, and the encoder turned while it was held (which cancels the click on release). |
| `drag_window`, `drag_anchor`, `drag_end` | A push-and-turn selection drag: the window it selects in (`None` when none is running), the index the range started at, and its moving end (see `selection.py`). |
| `pad_group` | The pad group (0–7 for A–H) chosen with the Group buttons. It picks the pads' notes, and its Group button is lit brightest. Starts on 3 (Group D), which holds middle C. |
| `sounding` | Pad id → the note sent when it was pressed, so its aftertouch and note-off use that note even if the group changes while it is held |
| `pad_mode` | The pad mode, `DEFAULT_PADS`, `KEYBOARD` or `SEQUENCER`, chosen with the encoder while the Pad Mode override is on; it stays when the override is off. Its layer is searched between the global mode's and base. |
| `fixed_velocity` | Toggled by F15, which is lit while it is on. Pads then play at full velocity (`pads.FIXED_VELOCITY`); note-offs and aftertouch are unchanged. |
| `note_repeat` | Note Repeat's mode in bridge mode: `note_repeat.OFF` (0, falsy), `ON` or `TRIPLETS`, cycled by its button, which is lit in On and Triplets. Sent to the bridge (as on/off plus the rate) by `BridgeLink`. Always `OFF` in hardware mode. While it isn't `OFF`, the encoder only changes `note_repeat_rate`. |
| `macro_values`, `macro_params`, `macro_logged` | Macros: each plugin parameter's running value and the value FL made of it, keyed by (plugin index, slot, parameter); each plugin's parameter names, looked up once; and what has been logged this session (parameter lists, missing names). |
| `note_repeat_rate` | Division index (0–3) into the current mode's `note_repeat.RATES`, default 2 (1/16 or 1/16T). Independent of FL's snap. |
| `fpc_channel` | The FPC channel selected at the last render, or `None`. Selecting a different FPC jumps the pads to Group E. |
| `menu_commands`, `menu_wait` | FL commands waiting for a popup menu to open, and the `OnIdle` ticks left before giving up. Set by `ui_commands.open_menu_then`. |
| `preset_hint` | After F13/F14: `(channel, old preset name, OnIdle ticks left)` until the new preset's name is shown, else `None`. Set by `presets.step`, cleared by `presets.show_preset_name`. |

`active_layers()` returns the binding layers to search, highest priority first: `[mode, pad_mode, "base"]`, e.g. `["shift", "default", "base"]`, or `[pad_mode, "base"]` when no global mode is on. The global mode comes first, so Shift pads work in every pad mode.

### Frames

A frame is a dict from control id to the LED's desired value:

- **Mono LEDs:** `True` (bright) or `False` (dim).
- **HSB LEDs:** a `(hue, saturation, brightness)` tuple of 0–127 values, built with [colors.py](flc_maschine/rendering/colors.py), e.g. `colors.rgb_to_hsb(fl.channel_color)`.
- **Missing entries** mean off.

## 5. Design rules

| Rule | Why |
|---|---|
| MIDI numbers appear only in `controls.py`. | A template change touches one file, and the tests can check it. |
| Only `rendering/output.py` sends MIDI to the controller (and, in bridge mode, `bridge_link.py` to the bridge on channel 16). | No two pieces of code can fight over an LED. |
| Every input first passes the `FeedbackGuard`. Messages that no MK2 control sends are marked handled, not passed to FL. | If FL's MIDI settings route the script's output back in, the LED messages look like presses (and CC 7 is channel volume). Without the guard the loop runs away: Scene or Play toggling, pads retriggering, volume maxed. |
| Handlers change state; they never touch LEDs. | LEDs are always a function of the current state, whatever changed it: a button, the mouse or another controller. |
| The renderer calls no FL functions. It reads FL state from the `FlSnapshot` it is given. | Rendering is testable without FL Studio, and FL is read once per render. |
| Every README control has a binding, even if it is `unimplemented(...)`. | Pressing anything gives a clear log line, and `bindings.py` doubles as a to-do list. |
| A control with no binding in any active layer passes through to FL. | The E1–E16 knobs can be linked to plugin parameters with FL's "Link to controller". |
| The dispatcher sets `handled = True` before calling a handler. A handler that wants FL to process the message too calls `ev.pass_to_fl()`. | Handled is the safe default: a scripted button should not also move a linked control. |
| A release, and pad aftertouch, go to the handler that took the press. Only `GATE` controls are tracked, because only they send releases. | Toggling shift while a pad is held would otherwise swallow the pad's note-off and leave a stuck note. |
| A pad's note-off and aftertouch use the note sent at press (`state.sounding`), not the current group's note. | Changing group while a pad is held would otherwise leave the first note stuck. |
| A pressed control's cached LED value is forgotten before rendering. | Buttons set to LED "For MIDI Out" light themselves; resending restores the script's state. |
| Handler exceptions are caught, logged with a traceback, and do not stop the script. | One bug in one handler cannot disable the controller. |
| Pad aftertouch never triggers a render. | Held pads send it continuously, and it never changes an LED; rendering on it meant hundreds of FL reads per second. |
| No FL reads while `general.safeToEdit()` is false; the render waits for `OnIdle`. | Querying channels and plugins during dialogs, the plugin picker or channel creation is a suspected crash cause (Novation's script guards the same way). |
| FL state is read, and LEDs are written, only from `OnIdle` (and `OnInit`). `OnMidiMsg` and `OnRefresh` just mark the controller dirty, and handlers use the last snapshot (`controller.fl`) rather than querying FL. | FL can run `OnMidiMsg` and `OnRefresh` at the same time on different threads; two renders reading FL and writing LEDs at once were the prime suspect for the crashes. |

## 6. Coupling to the Controller Editor template

In MIDI mode the MK2 sends exactly what `NI Maschine MK2/FL Complete.ncm2` says. `controls.py` mirrors it; the template is the source of truth.

**How events are decoded from each mode**

| Template mode | Hardware sends | Decoded as |
|---|---|---|
| `trigger` | On value at press | `press` |
| `toggle` | On and Off values on alternate presses | `press` for both, since each is one physical press |
| `gate` | On value at press, Off value at release | `press`, then `release` |
| Pad hit (`gate`, note) | Note on with velocity, then note off or velocity 0 | `press`, then `release` |
| Pad press (poly aftertouch) | Pressure on the pad's note | `pressure` |
| Encoder `comp` | 1 for +1, 127 for −1 | `turn` with `delta` |
| Encoder `absolute` | 0–127 | `value` |

**LEDs**

- **Mono LEDs** light when the script sends the control's own message with value 127, and dim with 0.
- **HSB LEDs** (pads and Group buttons) take three messages on the control's own number: hue on channel 0, saturation on channel 1 and brightness on channel 2, each 0–127. The template sets them to Color Mode = HSB with LED On = "For MIDI In", so they show only what the script sends and do not light when pressed. In the `.ncm2` file this is `color-mode="3"` on the three `<led>` elements and a `<behavior>` without `onIfDown`; `test_template.py` checks both.
- **HSB traffic.** NI's manual warns that heavy HSB traffic can make the controller briefly unresponsive. `LedWriter` sends only the components that changed, so a new channel colour usually resends just the hue. If lag ever appears when scrolling channels quickly, coalesce renders in `OnIdle`.

**Group buttons.** `<handleGroupControls />` in the template makes Group A–H ordinary CC buttons. Without it the hardware uses them to switch pad pages and sends no MIDI. Pad groups are handled in the script. The pads always send Pad Page A notes (12–27); [handlers/pads.py](flc_maschine/handlers/pads.py) rewrites each one to the selected group's note (`event.data1`) and leaves the event unhandled, so FL plays the new note on the selected channel. This is how the Akai Fire plays its note grids. Each group covers 16 notes, so the eight groups reach every MIDI note once:

| Group | A | B | C | D | E | F | G | H |
|---|---|---|---|---|---|---|---|---|
| Notes | 0–15 | 16–31 | 32–47 | 48–63 | 64–79 | 80–95 | 96–111 | 112–127 |

Middle C (60, C5 in FL Studio) is Group D's pad 13, and the script starts on Group D. The selected group's button is lit brightest.

**FPC mode.** In Default pad mode, while the selected channel is FPC ([fpc.py](flc_maschine/fpc.py) checks `plugins.getPluginName`), the pads play FPC's own pads instead (Keyboard pad mode plays FPC chromatically, like any channel):

- **Banks.** Group E plays bank A (FPC pads 0–15) and Group F plays bank B (16–31). The mapping is `FPC_BANK_FOR_GROUP` in [notes.py](flc_maschine/notes.py). FPC numbers its pads from the bottom left, like the MK2, so pad *n* plays FPC pad *n* − 1 of the bank.
- **Notes and empty pads** come from `plugins.getPadInfo`, and **colours** from `plugins.getColor` with `GC_Semitone`, so re-assigned or recoloured FPC pads are followed. Empty pads are dark and silent. `getPadInfo`'s colour option returns the same values; Novation's FLkey script uses `getColor`. **Known issue:** FL Studio returns the same grey for every bank B pad from both calls, so Group F's pads light grey. See [known-issues.md](known-issues.md).
- **Other groups.** A–D, G and H are dark and silent, and their Group buttons are off.
- **Auto-jump.** Newly selecting an FPC channel jumps to Group E, the bank A group. Only in Default pad mode, which is also the only mode that records the FPC, so turning back to Default on an FPC jumps then.

The Akai Fire hard-codes FPC's default notes instead; the Novation FLkey 2 queries FPC the same way. The snapshot reads both banks (64 plugin calls) on every render while FPC is selected. If that proves slow, cache the banks and re-read them on the plugin colour and name refresh flags.

**Changing the template**

1. Edit it in Controller Editor and export over `NI Maschine MK2/FL Complete.ncm2`.
2. Update the matching `Control` in `controls.py`.
3. Run the tests. `test_template.py` fails on any mismatch in message type, number, channel or mode.

**Template changes still needed**

- E1–E16 are `absolute`. Relative (`comp`) suits endless encoders better.

## 7. Extending the script

### Implement a README function

Write the handler in a module under `handlers/`, grouped by area, and swap it in for the `unimplemented(...)` entry in `bindings.py`. For example, the window buttons in [handlers/windows.py](flc_maschine/handlers/windows.py):

```python
def toggle(window):
    @on_press
    def handler(controller, ev):
        if ui.getFocused(window):
            ui.hideWindow(window)
        else:
            ui.showWindow(window)
            ui.setFocused(window)

    return handler
```

```python
# flc_maschine/bindings.py
_base = {
    ...
    "F5": windows.toggle(midi.widChannelRack),
    ...
}
```

A handler is any function `handler(controller, ev)`. It receives every event for its control: presses, releases, turns and so on. Wrap it in `on_press` if it should only act on presses. Put shift-mode behaviour in `_shift` under the same control id.

### Add an encoder override

Volume, Swing, Tempo, Navigate, Pattern, Grid and Pad Mode are toggled overrides for the master encoder ([handlers/encoder.py](flc_maschine/handlers/encoder.py)). To add another:

1. Write a function that takes the controller state and the encoder's signed `delta` and adjusts something, and add it to `MODES` under the id of the button that should toggle it:

   ```python
   def _pattern(state, delta):
       transport.globalTransport(midi.FPT_PatternJog, delta)


   MODES = {
       ...
       "PATTERN": _pattern,
   }
   ```

2. Bind the button in `bindings.py`: `"PATTERN": encoder.toggle_mode("PATTERN")`. Pass `hint=` to show something as the override turns on, as Pad Mode does.

The renderer's `_encoder_mode` rule lights whichever button's mode is active, so no LED code is needed.

### Light an LED

Add a rule to `RULES` in `renderer.py`. A rule sets frame entries from the state and the snapshot, and later rules override earlier ones. For example, the window buttons light from the snapshot's focused window:

```python
def _focused_window(state, fl, frame):
    button = WINDOW_BUTTONS.get(fl.focused_window)
    if button:
        frame[button] = True


RULES = [
    _channel_color,
    _pad_layer,  # pads bound to placeholders in the pad mode's layer go dark
    _keyboard_pads,  # Keyboard pad mode: piano-key colours
    _focused_window,
    _transport,
    _channel_state,
    _pad_mode,
    _encoder_mode,
    _mode_highlight,  # last: while Shift or New is on it replaces the other rules' lights
]
```

If a rule needs FL state the snapshot does not have, add a field to `FlSnapshot` and read it in `FlSnapshot.read()`. Keep FL calls out of the rule itself.

### Add a layer or mode

Shift and New mode are the worked examples. A global mode needs:

1. **A name** in `state.py` (e.g. `NEW = "new"`). `ControllerState.mode` holds the active one, and `active_layers()` puts its layer ahead of `base`.
2. **A binding layer** in `bindings.py`: a table of control id → handler, added to `LAYERS` and `MODE_CONTROLS`. Controls without an entry fall through to `base`. `MODE_CONTROLS` skips `unimplemented(...)` placeholders, so a control lights only once its function is real; bind a placeholder rather than nothing when the control must stay silent in the mode.
   Optionally give highlighted RGB controls a colour in `renderer.MODE_COLORS`.
3. **A toggle button:** `"F4": modes.toggle(NEW)`.
4. **Its button(s) in `renderer.MODE_BUTTONS`** (a tuple: Shift has F3 and F11), so `_mode_highlight` lights it and the controls in its layer while it is on.

Wrap a layer's handlers in `modes.once(...)` to make the mode one-shot, as New mode does.

**A pad mode** (Keyboard, Sequencer) is a layer too, but it isn't toggled or highlighted: `state.pad_mode` names it, the Pad Mode override picks it (`pad_modes.step`), and `active_layers()` puts it between the global mode and base, so it replaces only the controls it binds. To write one, replace its placeholders in `bindings.py`, remove it from `pad_modes.NOT_WRITTEN`, and add renderer rules for its lights (placeholder pads are dark through `_pad_layer`). If its pad handlers are marked `plays_notes` (as `pads.play` and `pads.play_keyboard` are), the bridge repeats them automatically (`pads_play_notes`). Keyboard is the written example: its layer binds `pads.play_keyboard`, and `renderer._keyboard_pads` lights it.

### Use another FL module

Import it where it is used. The tests need a stand-in, so add a module to `tests/fl_stubs/` with the functions and constants the script calls.

## 8. Testing

From the `FL Complete` folder:

```bash
python3 -m unittest discover -s tests -v
```

**`test_bridge.py`** tests [mk2_bridge/bridge.py](mk2_bridge/bridge.py) without MIDI ports or `mido`, with a fake clock:
- `Bridge`: MK2 messages reach FL unchanged; FL messages reach the MK2 except clock, transport and channel-16 messages, which drive the repeater; hello; a held pad replayed; a failed send is logged rather than raised.
- `NoteRepeater`: off means no tracking; timer-mode repeats and half-cell gates; a release passed only while the note is on; rate and tempo applied on the LSB; clock-mode hits on grid lines, skipping one just after the press; song-position jumps; one hit at a loop wrap's downbeat; no second hit at a re-sent position; rate changes on the clock (next grid line, spaced) and on the timer (from the last hit); the no-clock warning once per play, and none while clocks arrive (also through `Bridge`, as CC 126); the first note: played at once within the grace window and counted as that line, held back to the next line otherwise (also through `Bridge`), quick taps playing one note, held notes played by the timer if the clock stops, and the grace window's scaling and cap; falling back to the timer on stop or a silent clock; turning off releasing notes; independent pads.
- Clock smoothing (`ClockSmoothingTest`, simulating ticks rounded up to 512-sample buffer boundaries): repeats within 1.5 ms of even (the raw ticks jitter by about a buffer); a late tick doesn't delay its grid line; the model stops `MAX_AHEAD` past the last tick, then the timer takes over; a loop wrap keeps the phase with no double hit; a tempo change applies at once; the `--timing` report. The clock-mode `NoteRepeaterTest` cases run at 125 BPM, where a tick is exactly 20 ms, and step the timer at each tick.
- Pad pressure thinning (`PressureThinningTest`): repeated values dropped; at most one per interval, with the latest sent by the timer; 0 at once; a release drops pending pressure; pads thinned separately and other messages never; the heavy-traffic warning above `FLOOD_WARN`, and not below.
- Port-name matching (excluding the bridge's own ports, errors listing the ports found), and a clear message when `mido` isn't installed.

**`test_template.py`** parses `FL Complete.ncm2` and checks five things:

- Every `Control` matches its template element: message type, number, channel and mode.
- Pad and Group LEDs are in HSB mode and driven by the script ("For MIDI In").
- Each pad's pressure message uses the pad's note.
- `<handleGroupControls />` is present.
- No two controls share a message or an id.

**`test_scaffold.py`** imports the entry script with the stubs on `sys.path` and feeds it fake events. It covers:

- LEDs at init and deinit.
- Pads and Group buttons in the selected channel's colour, the bright Group button following the selection, and only changed HSB components being resent.
- `colors.rgb_to_hsb` conversions.
- F3 toggling shift and its LED, F11 as a second Shift with both lit; F1, F2, F9 and F10 sending Menu, Escape, Item Menu and Escape (F1 the plain menu in every window); F15 toggling fixed velocity and its LED; Master Left, Right and Enter sending their commands; Enter in the Channel Rack opening the selected channel's plugin (nothing without a selection; popup menus still get Enter).
- Shift mode (`ShiftModeTest`): Shift + Browse opening the plugin picker; only F3, F11 and controls with an implemented shift function lit (ALL's placeholder dim), shift pads in their function colours even in FPC mode, Group buttons dark, and state lights returning when shift turns off.
- Render scheduling (`RenderSchedulingTest`): `OnMidiMsg` and `OnRefresh` neither read FL nor write LEDs, many events cause one render on the next idle, pressed LEDs are reasserted then, and FPC pad presses use the snapshot.
- Crash mitigations (`CrashMitigationTest`): no render on aftertouch; no FL reads while unsafe, and the catch-up render from `OnIdle`.
- Diagnostics (`DiagnosticsTest`): header, callback and MIDI lines, `OnIdle` counted but not written, the stats line with memory counters, full garbage collections logged (and the hook registered only once), and exceptions logged then re-raised.
- Transpose (`TransposeTest`): semitone and octave steps moving the selected channel's pitch, the range widened (never narrowed) when needed, the ±48 clamp, the hint message, nothing without a selected channel, pads still playing their own notes, and Pads 13–16 lit and working on an FPC channel. The `channels` stub keeps each channel's normalised pitch and range.
- Shift pads (`ShiftPadTest`): Pad 1/2 undo/redo, Pad 3 compare (`general.undo`), Pad 5 quantize (selected channel only), Pad 7/8 tempo −/+0.1 BPM, Pad 9 clear (delete), Pad 10 cut (lit yellow), Pad 6 dark and silent, Pad 11/12 copy/paste, no notes from any pad in shift mode, and placeholder pads dark.
- New mode (`NewModeTest`): F4 toggling and replacing Shift, New + Browse (Menu, then Right ×3 sent from `OnIdle` once the menu is open, or dropped if it never opens) and New + Pattern (new pattern) turning the mode off, other controls acting normally, and New-mode lights.
- Mixer tracks (`MixerTrackTest`): F16 routing to the first empty track and copying the channel's name and colour; tracks with effects or a name skipped; several channels getting a track each; a routed channel moving on; channels in other groups keeping their tracks; the "Current" track never used; running out of tracks; no selection.
- Presets (`PresetTest`): F13/F14 stepping the selected channel's plugin; the name hint waiting for FL's asynchronous change, or shown after `PRESET_WAIT_TICKS`; the no-selection, no-plugin and no-presets hints; F13, F14 and F16 unlit.
- Duplicate (`DuplicateTest`): cloning the current pattern, selecting it first when the Picker selection is elsewhere.
- Push-and-turn selection (`EncoderDragSelectTest`): Channel Rack and Mixer ranges growing and shrinking across the anchor, their limits (the mixer's "Current" track left out), hints, a click acting only on release and not after a drag, turning while held elsewhere or in a popup menu navigating as usual, the drag taking priority over an override, and plain turns still navigating. The `mixer` stub keeps the current track and selected tracks. `EncoderTest.click()` pushes and releases, since the push acts on release.
- Entry scripts (`EntryScriptsTest`): each file's `# name=` line and bridge flag. Hardware mode (`HardwareModeTest`): Note Repeat is a placeholder, and nothing is sent on channel 16. Bridge mode (`BridgeModeTest`, driving the Bridge entry script): the full state on init; Note Repeat cycling Off → On → Triplets (LED, hints, CCs); the encoder changing the division within each mode (clockwise faster, clamped, hint, CCs); the division carrying across modes and taking priority over overrides, selection and navigation, with the encoder unchanged while Note Repeat is off; the snap no longer affecting the rate; play state sent; the no-clock hint shown once; tempo in tenths, normalised; nothing resent when unchanged; the hello resending everything; the periodic re-check while Note Repeat is on; repeat-off on deinit.
- Color mode (`ColorModeTest`): F12 toggles it and its LED; Color, Shift and New replace each other; entering it clears an encoder override; the pads show the palette with the current colour brightest (Group buttons dark), also on an FPC channel; a pad colours every selected channel and stays in the mode; the no-selection hint; no notes from the pads. In bridge mode, entering any mode sends CC 5 = 0 and leaving it 127. In `test_bridge.py`, pads that are functions pass straight through, and a mode turning on stops repeating pads.
- Feedback guard (`FeedbackGuardTest`):
  - an echoed colour message trips it at once and warns once
  - once tripped, input is ignored and nothing is sent
  - a pad loop stops at once, and a Scene loop on channel 1 stops after `ECHO_LIMIT` echoes
  - ordinary repeated presses don't trip it
  - in bridge mode, its own channel-16 messages trip it but the hello doesn't; hardware mode ignores channel 16
  - reloading starts clean
  - FL's All Notes Off on all 16 channels doesn't trip it, and isn't logged or dispatched
  - the trip warning names the message that tripped it

  The bridge's hello also resends every LED (`BridgeModeTest`).
- Shift and New additions: Shift + All saves, Shift + Note Repeat taps tempo (also in bridge mode, without toggling Note Repeat), Shift + Restart toggles loop recording, Shift + Select opens the selected channel's Piano Roll (`ui.openEventEditor` with `REC_Chan_PianoRoll` / `EE_PR`; nothing with no channel), and New + All saves a new version and ends New mode. Their LEDs are covered by the shift- and new-mode light tests.
- Macros (`MacroKnobsTest`, with test mappings; `MacroMappingsTest` checks the real ones have at most 8 entries and no parameter twice): named and numbered parameters stepped with `PIM_None` and the "name: value" hint; the current value written first; a focused mixer effect first; stepped parameters moving once the steps add up; restarting after a change elsewhere; clamping; unused and missing knobs (missing logged once); an unmapped (or empty) plugin's hint and one-time parameter log; Sampler channel macros as REC events; no target; the same in Shift mode.
- Channel knobs (`ChannelKnobsTest`): E1–E3 and E5–E7 step their own REC event on the selected channel, both ways, with the show-hint flags; E4 sets the pitch range a semitone per message, clamped 1–48, with the hint; E8 routes one track per message, clamped at Master and before "Current", with the hint; nothing without a selected channel; the same in Shift mode; E9 still passes through.
- Solo and Mute (`SoloMuteTest`): toggling the selected channel's solo and mute, their LEDs following the channel's state, the selection and changes made in FL, and nothing without a selected channel.
- Window buttons (`WindowButtonsTest`): focusing and hiding, one lit button per focused window, and focus changes made outside the script.
- Transport (`TransportTest`): Play/Rec and their LEDs, Scene switching pattern/song mode and its LED, Restart, Metro and Count-In on shift, snap step sizes, Step Left/Right grid movement, and ERASE still unimplemented.
- Encoder (`EncoderTest`): override toggling and switching with their LEDs, master volume steps and clamping, swing, tempo, window, pattern and snap jogs, entering Shift or New clearing the override, navigation and push per focused window, popup menus taking priority, and overrides taking priority over navigation.
- LED reassertion after a press.
- Pads passing through to FL at the selected group's notes; every note 0–127 reachable exactly once; note-off and aftertouch using the note sent at press, across group and shift changes.
- Keyboard pad mode (`KeyboardModeTest`): chromatic notes for the selected group, release and aftertouch on the sounding note, fixed velocity; pads lit as piano keys (C white, black keys at `BLACK_KEY_BRIGHTNESS`); an FPC channel played and lit chromatically with all Group buttons lit and no jump; back to Default on an FPC jumping to Group E; Shift pads overriding.
- Pad modes (`PadModeTest`): Pad Mode toggling the override (not fixed velocity) with a hint; turning through Default, Keyboard and Sequencer, one per message and stopping at the ends; the choice staying after the override; Sequencer pads silent, logged and dark with Group buttons still working; Shift pads in any pad mode; Default playing again; Shift clearing the override. In bridge mode, CC 5 = 0 in Sequencer and 127 in Keyboard and Default.
- F15 fixed velocity: toggling and its LED, note-ons at 127 with the note still translated, note-offs and aftertouch unchanged, and FPC mode too.
- FPC mode (`FpcModeTest`): the jump to Group E, both banks' notes and colours, empty pads, silent and dark other groups, and returning to the chromatic layout.
- Shifted pads being handled by the script.
- A release following its press across a shift toggle.
- Logging of unimplemented controls.
- Knob and unmapped-message pass-through.
- Every control in both layers running without errors.
- A refresh with no changes sending nothing.

**Stubs.**
- `device.sent` records every message the script sends; `device.reset()` clears it.
- `ui.focused`, `ui.snap_mode`, `transport.playing`, `transport.recording`, `transport.song_pos`, `general.ppq`, `general.ppb`, `channels.selected`, `channels.colors`, `plugins.names` and `plugins.pads` can be set to simulate FL's state. `ScriptTestCase.setUp` resets them.
- `transport.calls` records the transport calls the script makes, in order.

**In FL Studio.**
1. Assign "FL Complete Maschine MK2 (Hardware)" to the MK2's own port, or "(Bridge)" to `MK2 Bridge In` with the bridge running, in MIDI Settings.
2. Open VIEW > Script output. The script logs every unimplemented press, unbound control and unmapped message there.
3. To see every raw message, set `TRACE_MIDI = True` in [log.py](flc_maschine/log.py) and reload the script.

## 9. Porting from the old MK2 script

The older script in the sibling `NI Maschine MK2` folder already implements much of the README. Its handlers map onto this structure as follows:

| Old code | New home |
|---|---|
| `navigation.handle_channels` / `pianoroll` / `playlist` / `mixer` / `browse`, `ui_windows.hideOrShowUiWindow` | Ported: [handlers/windows.py](flc_maschine/handlers/windows.py), bound to F5–F8 and BROWSE |
| `encoder.py` turn and click handlers | Ported: [handlers/encoder.py](flc_maschine/handlers/encoder.py), bound to ENCODER and ENCODER_PUSH. The per-window behaviour is in the `NAVIGATION` and `PUSH` tables, and the old overrides are in `MODES` (Volume, Swing, Tempo, Navigate, Pattern, Grid). The old Scene arrangement jog was dropped: Scene now switches pattern/song mode (`transport_controls.toggle_song_mode`). |
| `master.handle_volume` / `swing` / `tempo` | Ported: `encoder.toggle_mode`, bound to VOLUME, SWING and TEMPO (toggled, as in the old script) |
| `master.handle_mleft` / `mright` / `enter` | Ported: `ui_commands.send` with `FPT_Left`, `FPT_Right` and `FPT_Enter`. The old Enter sent `FPT_Menu` in the Browser; that exception isn't ported yet. |
| `transport_controls.py` | Ported: [handlers/transport_controls.py](flc_maschine/handlers/transport_controls.py). Step Left/Right now size steps from FL's timebase instead of a fixed tick table. GRID is now the snap encoder override; ERASE is not ported yet. |
| `pads.handle_mute` / `handle_solo` | MUTE and SOLO handlers |
| `groups.handle_group` | Not ported: Group buttons now select pad groups ([handlers/groups.py](flc_maschine/handlers/groups.py)) |
| `leds._render_focused_ui_window` and the other `_render_*` functions | Renderer rules |

When porting:
- Replace the old numeric window indexes with `midi.widMixer`, `midi.widChannelRack` and the other constants.
- Drop the `event.handled = True` lines, because the dispatcher sets it.
- Drop the `leds.render(...)` calls, because rendering happens after every event.
