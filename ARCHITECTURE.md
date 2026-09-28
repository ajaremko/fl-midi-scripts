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
│   ├── handlers/
│   │   ├── common.py              unimplemented, passthrough, on_press
│   │   ├── groups.py              select (Group A–H)
│   │   ├── transport_controls.py  Restart, Play/Metro, Rec/Count-In, Step Left/Right
│   │   ├── windows.py             toggle (BROWSE, F1–F4)
│   │   ├── pads.py                play: translate pad notes for the selected group
│   │   └── modes.py               toggle_shift
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
                      leds.invalidate(control id)        (presses and releases only)
                        │
                        ▼
                      dispatcher.dispatch ── bindings.lookup(state, control id)
                        │                     walks state.active_layers()
                        │                     no binding ──▶ log "no binding", FL handles it
                        ▼
                      handler(controller, ev) ──▶ changes ControllerState and/or calls FL Studio
                        │
                        ▼
 OnRefresh(flags) ──▶ MaschineMk2.render
                        │
                        ▼
                      renderer.render(state, FlSnapshot.read()) ──▶ frame {control id: value}
                        │
                        ▼
                      LedWriter.write(frame) ── diff against last sent ──▶ device.midiOutMsg ──▶ MK2
```

1. **Decode.** [events.decode](flc_maschine/events.py) finds the control by (message type, channel, number) and turns the raw message into a `ControlEvent` using the control's template mode (see [section 6](#6-coupling-to-the-controller-editor-template)).
2. **Invalidate.** Some buttons light themselves when pressed. After a press or release, the controller forgets what it last sent to that LED, so the next render sends the state the script wants.
3. **Dispatch.** [dispatcher.dispatch](flc_maschine/dispatcher.py) finds the handler in the highest-priority active layer, marks the event handled and calls it inside `try/except`.
4. **Handle.** The handler changes `ControllerState`, calls FL Studio, or hands the message back to FL with `ev.pass_to_fl()`.
5. **Render.** The controller reads an `FlSnapshot` of FL Studio and lets [pads.follow_fpc_selection](flc_maschine/handlers/pads.py) react to it (jumping to Group E when an FPC is newly selected). Then [renderer.render](flc_maschine/rendering/renderer.py) builds a frame from the state and the snapshot.
6. **Output.** [LedWriter.write](flc_maschine/rendering/output.py) sends only the LEDs whose value differs from what it last sent.

The other callbacks:

| Callback | What happens |
|---|---|
| `OnInit` | Log the port, forget every cached LED value, render. The first frame turns off every LED except those the rules light. |
| `OnRefresh` | Render. FL calls it when its state changes, including window focus, and the diff keeps it cheap. |
| `OnIdle` | Nothing yet. It is the hook for timed features such as long presses or blinking. |
| `OnDeInit` | Write an empty frame, which turns every LED off. |

## 4. Modules

| File | Responsibility | Key names | Uses FL modules |
|---|---|---|---|
| [controls.py](flc_maschine/controls.py) | Every control, its README label and the MIDI message the template makes it send. The only place MIDI numbers appear. | `Control`, `ALL_CONTROLS`, `BY_ID`, `BY_KEY`, `LED_CONTROLS`, `PADS` | No |
| [bindings.py](flc_maschine/bindings.py) | Which handler runs for each control in each layer | `LAYERS`, `lookup` | `midi` constants |
| [state.py](flc_maschine/state.py) | Mutable controller state | `ControllerState`, `active_layers`, `BASE`, `SHIFT` | No |
| [notes.py](flc_maschine/notes.py) | Which note each pad plays: 16 notes per group, Group A from 0; which FPC bank and pad each group and pad maps to | `pad_note`, `PAD_INDEX`, `NOTES_PER_GROUP`, `FPC_BANK_FOR_GROUP`, `fpc_pad` | No |
| [fpc.py](flc_maschine/fpc.py) | Detect a selected FPC and read its pads | `selected_fpc_channel`, `read_pad`, `read_banks`, `FpcPad` | `channels`, `midi`, `plugins` (reads only) |
| [events.py](flc_maschine/events.py) | Decode raw MIDI into control events | `ControlEvent`, `decode`, `PRESS`, `RELEASE`, `TURN`, `VALUE`, `PRESSURE` | `midi` constants |
| [dispatcher.py](flc_maschine/dispatcher.py) | Route an event to its handler; release and aftertouch follow the press; fault isolation | `dispatch` | No |
| [controller.py](flc_maschine/controller.py) | Owns the state and the LED writer; implements the FL callbacks | `MaschineMk2` | `device` |
| [log.py](flc_maschine/log.py) | `[FLC MK2]` prefixed output; optional raw MIDI trace | `info`, `trace_midi`, `TRACE_MIDI` | No |
| [handlers/common.py](flc_maschine/handlers/common.py) | Reusable handlers and wrappers | `unimplemented`, `passthrough`, `on_press` | No |
| [handlers/modes.py](flc_maschine/handlers/modes.py) | Handlers that change the controller's own modes | `toggle_shift` | No |
| [handlers/groups.py](flc_maschine/handlers/groups.py) | Group A–H buttons: select the pad group | `select` | No |
| [handlers/transport_controls.py](flc_maschine/handlers/transport_controls.py) | Transport buttons. Step Left/Right move to the previous/next grid line of FL's main snap (`ui.getSnapMode`), sized from FL's timebase (`general.getRecPPQ`, `getRecPPB`). The position is read with `mixer.getSongTickPos()`, because `transport.getSongPos` stays at 0 in Song mode while stopped ([known-issues.md](known-issues.md)) | `restart`, `play`, `record`, `metronome`, `count_in`, `step_left`, `step_right`, `snap_ticks`, `next_position` | `transport`, `general`, `mixer`, `ui`, `midi` |
| [handlers/windows.py](flc_maschine/handlers/windows.py) | BROWSE and F1–F4: show and focus a window, or hide it if already focused | `toggle` | `ui` |
| [handlers/pads.py](flc_maschine/handlers/pads.py) | Pads: rewrite the note to the selected group's note and pass it to FL | `play` | No |
| [rendering/fl_state.py](flc_maschine/rendering/fl_state.py) | Read FL Studio's state once per render: focused window, transport, selected channel's colour, selected FPC and its pads | `FlSnapshot`, `WINDOWS` | `midi`, `ui`, `transport`, `channels`, and `plugins` through `fpc.py` (reads only) |
| [rendering/renderer.py](flc_maschine/rendering/renderer.py) | Decide every LED's value | `render`, `RULES`, `WINDOW_BUTTONS`, `LIT_BRIGHTNESS`, `DIM_BRIGHTNESS` | `midi` constants; no calls |
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
| `shift` | Latched by F5. While on, the `shift` layer takes priority over `base`. |
| `held` | Control id → the handler that took its press, for gate controls currently held down |
| `encoder_mode` | Reserved: what the master encoder controls while Volume, Swing or Tempo is held |
| `pad_group` | The pad group (0–7 for A–H) chosen with the Group buttons. It picks the pads' notes, and its Group button is lit brightest. Starts on 3 (Group D), which holds middle C. |
| `sounding` | Pad id → the note sent when it was pressed, so its aftertouch and note-off use that note even if the group changes while it is held |
| `fpc_channel` | The FPC channel selected at the last render, or `None`. Selecting a different FPC jumps the pads to Group E. |

`active_layers()` returns the binding layers to search, highest priority first: `["shift", "base"]` or `["base"]`.

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

- Volume, Swing and Tempo are `trigger`, so they send no release and "hold + turn" cannot be detected. Set them to `gate`.
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

### Add a hold modifier (Volume + encoder)

1. Set Volume to `gate` in the template, and `GATE` in `controls.py`.
2. Bind a handler that records the mode while the button is held:

   ```python
   def hold_encoder_mode(mode):
       def handler(controller, ev):
           if ev.is_press:
               controller.state.encoder_mode = mode
           elif ev.is_release:
               controller.state.encoder_mode = None

       return handler
   ```

3. In the ENCODER handler, branch on `controller.state.encoder_mode` and use `ev.delta` for the step.
4. Add a renderer rule so Volume lights while held: `frame["VOLUME"] = state.encoder_mode == "VOLUME"`.

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
    _shift_indicator,
]
```

If a rule needs FL state the snapshot does not have, add a field to `FlSnapshot` and read it in `FlSnapshot.read()`. Keep FL calls out of the rule itself.

### Add a layer or mode

1. Add a layer name in `state.py` and a table for it in `LAYERS`.
2. Add whatever flag switches it on to `ControllerState`.
3. Include it in `active_layers()` at the right priority.

Controls without an entry in the new layer fall through to the layers below it.

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
- F5 toggling shift and its LED.
- Window buttons (`WindowButtonsTest`): focusing and hiding, one lit button per focused window, and focus changes made outside the script.
- Transport (`TransportTest`): Play/Rec and their LEDs, Restart, Metro and Count-In on shift, snap step sizes, Step Left/Right grid movement, and GRID/ERASE still unimplemented.
- LED reassertion after a press.
- Pads passing through to FL at the selected group's notes; every note 0–127 reachable exactly once; note-off and aftertouch using the note sent at press, across group and shift changes.
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
| `encoder.py` turn and click handlers | ENCODER and ENCODER_PUSH handlers, branching on `state.encoder_mode` and the focused window |
| `master.handle_volume` / `swing` / `tempo` | Hold modifiers on VOLUME, SWING and TEMPO (after the template changes them to `gate`) |
| `transport_controls.py` | Ported: [handlers/transport_controls.py](flc_maschine/handlers/transport_controls.py). Step Left/Right now size steps from FL's timebase instead of a fixed tick table. GRID and ERASE not ported yet. |
| `pads.handle_mute` / `handle_solo` | MUTE and SOLO handlers |
| `groups.handle_group` | Not ported: Group buttons now select pad groups ([handlers/groups.py](flc_maschine/handlers/groups.py)) |
| `leds._render_focused_ui_window` and the other `_render_*` functions | Renderer rules |

When porting:
- Replace the old numeric window indexes with `midi.widMixer`, `midi.widChannelRack` and the other constants.
- Drop the `event.handled = True` lines, because the dispatcher sets it.
- Drop the `leds.render(...)` calls, because rendering happens after every event.
