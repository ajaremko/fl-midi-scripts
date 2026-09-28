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
├── device_FLC_MaschineMK2.py      entry script: header + FL callbacks, nothing else
├── flc_maschine/                  the MK2 script's package
│   ├── controls.py                hardware config: every control and the MIDI message it sends
│   ├── bindings.py                function config: which handler each control runs, per layer
│   ├── state.py                   ControllerState, shared by handlers and the renderer
│   ├── notes.py                   which note each pad plays in each pad group
│   ├── fpc.py                     reads the selected FPC's pads: note, colour, empty
│   ├── events.py                  raw FL event -> ControlEvent
│   ├── dispatcher.py              ControlEvent -> handler
│   ├── controller.py              MaschineMk2: wires the pieces together
│   ├── log.py                     prefixed printing to the Script output window
│   ├── diagnostics.py             crash log (flc_debug.log): callbacks, stats, exceptions
│   ├── handlers/
│   │   ├── common.py              unimplemented, passthrough, on_press
│   │   ├── edit.py                undo, redo, quantize (shift-mode pads)
│   │   ├── encoder.py             master encoder: navigate/push the focused window; Volume/Swing/Tempo overrides
│   │   ├── groups.py              select (Group A–H)
│   │   ├── transport_controls.py  Restart, Play/Metro, Rec/Count-In, Step Left/Right
│   │   ├── ui_commands.py         send / send_for_focus: one FL command per press (F5 Menu, F6 Esc)
│   │   ├── windows.py             toggle (BROWSE, F1–F4)
│   │   ├── pads.py                play: translate pad notes for the selected group
│   │   ├── modes.py               toggle (Shift / New), once (one-shot mode functions)
│   │   └── pattern_controls.py    new_pattern
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
- **Thin entry script.** [device_FLC_MaschineMK2.py](device_FLC_MaschineMK2.py) creates one `MaschineMk2` and forwards `OnInit`, `OnDeInit`, `OnMidiMsg`, `OnRefresh` and `OnIdle` to it. The `# name=` header must stay on line 1.
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
| `OnIdle` | Send queued menu commands once their menu is open (`ui_commands.run_menu_commands`). If dirty and `general.safeToEdit()` allows it, resend invalidated LEDs and render; while FL is busy (dialogs, the plugin picker, channels being added) it stays dirty and retries. Then `diagnostics.tick` writes its stats line. Also the hook for future timed features such as long presses or blinking. |
| `OnDeInit` | Write an empty frame, which turns every LED off. |

## 4. Modules

| File | Responsibility | Key names | Uses FL modules |
|---|---|---|---|
| [controls.py](flc_maschine/controls.py) | Every control, its README label and the MIDI message the template makes it send. The only place MIDI numbers appear. | `Control`, `ALL_CONTROLS`, `BY_ID`, `BY_KEY`, `LED_CONTROLS`, `PADS` | No |
| [bindings.py](flc_maschine/bindings.py) | Which handler runs for each control in each layer | `LAYERS`, `lookup` | `midi` constants |
| [state.py](flc_maschine/state.py) | Mutable controller state | `ControllerState`, `active_layers`, `BASE`, `SHIFT`, `NEW` | No |
| [notes.py](flc_maschine/notes.py) | Which note each pad plays: 16 notes per group, Group A from 0; which FPC bank and pad each group and pad maps to | `pad_note`, `PAD_INDEX`, `NOTES_PER_GROUP`, `FPC_BANK_FOR_GROUP`, `fpc_pad` | No |
| [fpc.py](flc_maschine/fpc.py) | Detect a selected FPC and read its pads | `selected_fpc_channel`, `read_pad`, `read_banks`, `FpcPad` | `channels`, `midi`, `plugins` (reads only) |
| [events.py](flc_maschine/events.py) | Decode raw MIDI into control events | `ControlEvent`, `decode`, `PRESS`, `RELEASE`, `TURN`, `VALUE`, `PRESSURE` | `midi` constants |
| [dispatcher.py](flc_maschine/dispatcher.py) | Route an event to its handler; release and aftertouch follow the press; fault isolation | `dispatch` | No |
| [controller.py](flc_maschine/controller.py) | Owns the state and the LED writer; implements the FL callbacks | `MaschineMk2` | `device` |
| [log.py](flc_maschine/log.py) | `[FLC MK2]` prefixed output; optional raw MIDI trace | `info`, `trace_midi`, `TRACE_MIDI` | No |
| [diagnostics.py](flc_maschine/diagnostics.py) | **Off by default (`ENABLED = False`).** Crash log that survives FL crashing: writes `flc_debug.log` (next to the entry script) a line at a time. The entry script runs every callback through `run` (counted, timed, `> name [t<thread id>]` and `< name` lines except for `OnIdle`, exceptions logged and re-raised); `tick` writes a stats line every 5 s (call counts, renders, state sizes). Memory counters (`MEMORY_STATS`) and full-GC logging (`WATCH_GC`) are optional and off by default: they were ruled out as useful, and are suspected of contributing to crashes. Never use `gc.get_objects()` here: it fails in FL's Python. Switch off with `ENABLED = False` | `run`, `note`, `count`, `tick`, `start`, `ENABLED`, `LOG_FILE` | `general` (version only) |
| [handlers/common.py](flc_maschine/handlers/common.py) | Reusable handlers and wrappers. `unimplemented(...)` handlers carry `placeholder = True`, so modes don't highlight them | `unimplemented`, `passthrough`, `on_press` | No |
| [handlers/edit.py](flc_maschine/handlers/edit.py) | Editing actions for the shift-mode pads: Pad 1 Undo (`general.undoUp`), Pad 2 Redo (`general.undoDown`) and Pad 5 Quantize (`channels.quickQuantize` on the selected channel; FL offers no quantize strength, so Pad 6 Quantize 50% can't exist) | `undo`, `redo`, `quantize` | `general`, `channels` |
| [handlers/modes.py](flc_maschine/handlers/modes.py) | Handlers that change the controller's own modes: `toggle(mode)` for F7/F8 (entering a mode also clears `encoder_mode`), and `once(handler)`, which turns the mode off after a New-mode function runs | `toggle`, `once` | No |
| [handlers/pattern_controls.py](flc_maschine/handlers/pattern_controls.py) | Pattern button functions. New + Pattern jumps to the next empty pattern | `new_pattern` | `patterns`, `midi` |
| [handlers/encoder.py](flc_maschine/handlers/encoder.py) | Master encoder. Turning navigates an open popup menu or the focused window (`NAVIGATION`); pushing does that window's action (`PUSH`). Volume, Swing, Tempo, Navigate, Pattern and Grid toggle an override mode that takes over turning to adjust master volume, swing or tempo, or jog between open windows, patterns or main snap settings (`MODES`) | `turn`, `push`, `toggle_mode`, `MODES`, `NAVIGATION`, `PUSH` | `channels`, `mixer`, `transport`, `ui`, `midi` |
| [handlers/groups.py](flc_maschine/handlers/groups.py) | Group A–H buttons: select the pad group | `select` | No |
| [handlers/transport_controls.py](flc_maschine/handlers/transport_controls.py) | Transport buttons. Step Left/Right move to the previous/next grid line of FL's main snap (`ui.getSnapMode`), sized from FL's timebase (`general.getRecPPQ`, `getRecPPB`). The position is read with `mixer.getSongTickPos()`, because `transport.getSongPos` stays at 0 in Song mode while stopped ([known-issues.md](known-issues.md)) | `restart`, `play`, `record`, `toggle_song_mode`, `metronome`, `count_in`, `step_left`, `step_right`, `snap_ticks`, `next_position` | `transport`, `general`, `mixer`, `ui`, `midi` |
| [handlers/ui_commands.py](flc_maschine/handlers/ui_commands.py) | Buttons that send one FL command per press. `send_for_focus` picks the command by focused window: F5 sends `FPT_ItemMenu` in the Browser and Piano Roll, otherwise `FPT_Menu`. F6 Esc sends `FPT_Escape`; Master Left, Right and Enter send `FPT_Left`, `FPT_Right` and `FPT_Enter`. `open_menu_then` opens a menu and queues follow-up commands, which `run_menu_commands` sends from `OnIdle` once FL reports the menu open (dropping them after `MENU_WAIT_TICKS`). New + Browse uses it to reach FL's Add menu: `FPT_Menu`, then `FPT_Right` ×3 ([known-issues.md](known-issues.md)) | `send`, `send_for_focus`, `open_menu_then`, `run_menu_commands` | `transport`, `ui` |
| [handlers/windows.py](flc_maschine/handlers/windows.py) | BROWSE and F1–F4: show and focus a window, or hide it if already focused | `toggle` | `ui` |
| [handlers/pads.py](flc_maschine/handlers/pads.py) | Pads: rewrite the note to the selected group's note and pass it to FL. While fixed velocity (Pad Mode) is on, note-ons are also rewritten to velocity `FIXED_VELOCITY` (127) | `play`, `toggle_fixed_velocity`, `FIXED_VELOCITY` | No |
| [rendering/fl_state.py](flc_maschine/rendering/fl_state.py) | Read FL Studio's state once per render: focused window, transport (playing, recording, song mode), selected channel's colour, selected FPC and its pads | `FlSnapshot`, `WINDOWS` | `midi`, `ui`, `transport`, `channels`, and `plugins` through `fpc.py` (reads only) |
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
| `mode` | The global mode: `SHIFT` (toggled by F8), `NEW` (toggled by F7, one-shot) or `None`. Only one is on at a time. Its layer takes priority over `base`, and only its button and the controls in `bindings.MODE_CONTROLS[mode]` (bound to a real function, not a placeholder) are lit, RGB ones in their `renderer.MODE_COLORS` colour. |
| `held` | Control id → the handler that took its press, for gate controls currently held down |
| `encoder_mode` | The master encoder's override mode, `"VOLUME"`, `"SWING"`, `"TEMPO"`, `"NAVIGATE"`, `"PATTERN"` or `"GRID"`, toggled by those buttons; `None` when off. The active button is lit. Entering Shift or New mode clears it. |
| `pad_group` | The pad group (0–7 for A–H) chosen with the Group buttons. It picks the pads' notes, and its Group button is lit brightest. Starts on 3 (Group D), which holds middle C. |
| `sounding` | Pad id → the note sent when it was pressed, so its aftertouch and note-off use that note even if the group changes while it is held |
| `fixed_velocity` | Toggled by Pad Mode, which is lit while it is on. Pads then play at full velocity (`pads.FIXED_VELOCITY`); note-offs and aftertouch are unchanged. |
| `fpc_channel` | The FPC channel selected at the last render, or `None`. Selecting a different FPC jumps the pads to Group E. |
| `menu_commands`, `menu_wait` | FL commands waiting for a popup menu to open, and the `OnIdle` ticks left before giving up. Set by `ui_commands.open_menu_then`. |

`active_layers()` returns the binding layers to search, highest priority first: `[mode, "base"]`, e.g. `["shift", "base"]`, or `["base"]` when no mode is on.

### Frames

A frame is a dict from control id to the LED's desired value:

- **Mono LEDs:** `True` (bright) or `False` (dim).
- **HSB LEDs:** a `(hue, saturation, brightness)` tuple of 0–127 values, built with [colors.py](flc_maschine/rendering/colors.py), e.g. `colors.rgb_to_hsb(fl.channel_color)`.
- **Missing entries** mean off.

## 5. Design rules

| Rule | Why |
|---|---|
| MIDI numbers appear only in `controls.py`. | A template change touches one file, and the tests can check it. |
| Only `rendering/output.py` sends MIDI to the controller. | No two pieces of code can fight over an LED. |
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

**FPC mode.** While the selected channel is FPC ([fpc.py](flc_maschine/fpc.py) checks `plugins.getPluginName`), the pads play FPC's own pads instead:

- **Banks.** Group E plays bank A (FPC pads 0–15) and Group F plays bank B (16–31). The mapping is `FPC_BANK_FOR_GROUP` in [notes.py](flc_maschine/notes.py). FPC numbers its pads from the bottom left, like the MK2, so pad *n* plays FPC pad *n* − 1 of the bank.
- **Notes and empty pads** come from `plugins.getPadInfo`, and **colours** from `plugins.getColor` with `GC_Semitone`, so re-assigned or recoloured FPC pads are followed. Empty pads are dark and silent. `getPadInfo`'s colour option returns the same values; Novation's FLkey script uses `getColor`. **Known issue:** FL Studio returns the same grey for every bank B pad from both calls, so Group F's pads light grey. See [known-issues.md](known-issues.md).
- **Other groups.** A–D, G and H are dark and silent, and their Group buttons are off.
- **Auto-jump.** Newly selecting an FPC channel jumps to Group E, the bank A group.

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
    "F1": windows.toggle(midi.widChannelRack),
    ...
}
```

A handler is any function `handler(controller, ev)`. It receives every event for its control: presses, releases, turns and so on. Wrap it in `on_press` if it should only act on presses. Put shift-mode behaviour in `_shift` under the same control id.

### Add an encoder override

Volume, Swing and Tempo are toggled overrides for the master encoder ([handlers/encoder.py](flc_maschine/handlers/encoder.py)). To add another:

1. Write a function that takes the encoder's signed `delta` and adjusts something, and add it to `MODES` under the id of the button that should toggle it:

   ```python
   def _pattern(delta):
       transport.globalTransport(midi.FPT_PatternJog, delta)


   MODES = {
       ...
       "PATTERN": _pattern,
   }
   ```

2. Bind the button in `bindings.py`: `"PATTERN": encoder.toggle_mode("PATTERN")`.

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
    _focused_window,
    _transport,
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
3. **A toggle button:** `"F7": modes.toggle(NEW)`.
4. **Its button in `renderer.MODE_BUTTONS`**, so `_mode_highlight` lights it and the controls in its layer while it is on.

Wrap a layer's handlers in `modes.once(...)` to make the mode one-shot, as New mode does.

### Use another FL module

Import it where it is used. The tests need a stand-in, so add a module to `tests/fl_stubs/` with the functions and constants the script calls.

## 8. Testing

From the `FL Complete` folder:

```bash
python3 -m unittest discover -s tests -v
```

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
- F8 toggling shift and its LED; F5 and F6 sending Menu and Escape; Master Left, Right and Enter sending their commands.
- Shift mode (`ShiftModeTest`): Shift + Browse opening the plugin picker; only F8 and controls with an implemented shift function lit (ALL's placeholder dim), shift pads in their function colours even in FPC mode, Group buttons dark, and state lights returning when shift turns off.
- Render scheduling (`RenderSchedulingTest`): `OnMidiMsg` and `OnRefresh` neither read FL nor write LEDs, many events cause one render on the next idle, pressed LEDs are reasserted then, and FPC pad presses use the snapshot.
- Crash mitigations (`CrashMitigationTest`): no render on aftertouch; no FL reads while unsafe, and the catch-up render from `OnIdle`.
- Diagnostics (`DiagnosticsTest`): header, callback and MIDI lines, `OnIdle` counted but not written, the stats line with memory counters, full garbage collections logged (and the hook registered only once), and exceptions logged then re-raised.
- Shift pads (`ShiftPadTest`): Pad 1/2 undo/redo, Pad 5 quantize (selected channel only), Pad 9 clear (delete), Pad 6 dark and silent, Pad 11/12 copy/paste, no notes from any pad in shift mode, and placeholder pads dark.
- New mode (`NewModeTest`): F7 toggling and replacing Shift, New + Browse (Menu, then Right ×3 sent from `OnIdle` once the menu is open, or dropped if it never opens) and New + Pattern (new pattern) turning the mode off, other controls acting normally, and New-mode lights.
- Window buttons (`WindowButtonsTest`): focusing and hiding, one lit button per focused window, and focus changes made outside the script.
- Transport (`TransportTest`): Play/Rec and their LEDs, Scene switching pattern/song mode and its LED, Restart, Metro and Count-In on shift, snap step sizes, Step Left/Right grid movement, and ERASE still unimplemented.
- Encoder (`EncoderTest`): override toggling and switching with their LEDs, master volume steps and clamping, swing, tempo, window, pattern and snap jogs, entering Shift or New clearing the override, navigation and push per focused window, popup menus taking priority, and overrides taking priority over navigation.
- LED reassertion after a press.
- Pads passing through to FL at the selected group's notes; every note 0–127 reachable exactly once; note-off and aftertouch using the note sent at press, across group and shift changes.
- Pad Mode fixed velocity: toggling and its LED, note-ons at 127 with the note still translated, note-offs and aftertouch unchanged, and FPC mode too.
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
1. Assign "FL Complete Maschine MK2 (user)" to the MK2's port in MIDI Settings.
2. Open VIEW > Script output. The script logs every unimplemented press, unbound control and unmapped message there.
3. To see every raw message, set `TRACE_MIDI = True` in [log.py](flc_maschine/log.py) and reload the script.

## 9. Porting from the old MK2 script

The older script in the sibling `NI Maschine MK2` folder already implements much of the README. Its handlers map onto this structure as follows:

| Old code | New home |
|---|---|
| `navigation.handle_channels` / `pianoroll` / `playlist` / `mixer` / `browse`, `ui_windows.hideOrShowUiWindow` | Ported: [handlers/windows.py](flc_maschine/handlers/windows.py), bound to F1–F4 and BROWSE |
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
