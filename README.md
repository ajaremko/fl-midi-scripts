# FL Complete MIDI Scripts

This repo contains 3 MIDI scripts for integrating the Akai Fire, Native Instruments Maschine MK2 and Novation FL Keys 2 with FL Studio in one cohesive control surface. Each controller's vendor supplied MIDI scripts try to pack as much functionality as possible into their hardware unit. This means that access to a specific functionality can require putting the controller into a particular state ("pad mode", "sequencer mode", etc), which can be cumbersome and requires keeping a mental model of distinct state spaces for each controller. 
These scripts attempt to solve this by allowing each controller to focus on controlling specific parts of FL studio rather than packing every functionality into every controller. The notable exception where functionality is genuinely meant to be redundant across controllers is transport control.

See [ARCHITECTURE.md](ARCHITECTURE.md) for how the scripts are built and organised, and [known-issues.md](known-issues.md) for problems we know about.

**FL Studio version:** use **FL Studio 2025**. FL Studio 2026 has known issues with these scripts (a hang after recording, and a crash when the record-options dialog opens); see [known-issues.md](known-issues.md).

## Maschine MK2

The maschine features 16 high-quality RGB drum pads, a large, tactile encoder knob and an array of buttons specifically for controlling the Maschine DAW. 

Of the 3 controllers, its responsible for 
- navigating between screens
- providing quick access to copy, paste, delete, etc
- master encoder for navigating within the active screen, menu or adjusting other parameters (many modes available)
- high-quality drum pads for recording

This allows the other two controllers to focus on doing what they do best - being a sequencer and a keyboard respectively.

### Hardware Layout Diagram

```text
 MASCHINE

 MIDI       INSTANCE                                                                                                         
┌────────┐ ┌────────┐        ┌────────┐ ┌────────┐ ┌────────┐ ┌────────┐     ┌────────┐ ┌────────┐ ┌────────┐ ┌────────┐   
│CONTROL │ │STEP    │        │F1      │ │F2      │ │F3      │ │F4      │     │F5      │ │F6      │ │F7      │ │F8      │   
└────────┘ └────────┘        └────────┘ └────────┘ └────────┘ └────────┘     └────────┘ └────────┘ └────────┘ └────────┘   
┌────────┐ ┌────────┐        ┌─────────────────────────────────────────┐     ┌─────────────────────────────────────────┐   
│BROWSE  │ │SAMPLING│        │LCD SCREEN 1                             │     │LCD SCREEN 2                             │   
└────────┘ └────────┘        │                                         │     │                                         │   
┌────────┐ ┌────────┐        │                                         │     │                                         │   
│<       │ │       >│        │                                         │     │                                         │      
└────────┘ └────────┘        └─────────────────────────────────────────┘     └─────────────────────────────────────────┘   
 SAVE                                                                                                                      
┌────────┐ ┌────────┐          /────\     /────\     /────\     /────\         /────\     /────\     /────\     /────\      
│ALL     │ │AUTO    │         (  E1  )   (  E2  )   (  E3  )   (  E4  )       (  E5  )   (  E6  )   (  E7  )   (  E8  )     
└────────┘ └────────┘          \____/     \____/     \____/     \____/         \____/     \____/     \____/     \____/      
                                                                                                                           
- MASTER ----------------------------------       - PADS ---------------------------------------------------------------
┌────────┐        -------         TAP                        13 SEMI+       14 SEMI-       15 OCTAVE-     16 OCTAVE+
│VOLUME  │       / +++++ \       ┌────────┐       ┌────────┐ ┌────────────┐ ┌────────────┐ ┌────────────┐ ┌────────────┐
└────────┘      / MASTER  \      │NOTE REP│       │SCENE   │ │            │ │            │ │            │ │            │
┌────────┐      \ ENCODER /      └────────┘       └────────┘ │            │ │            │ │            │ │            │
│TEMPO   │       \ +++++ /                                   │            │ │            │ │            │ │            │
└────────┘        -------                         ┌────────┐ │            │ │            │ │            │ │            │
┌────────┐ ┌────────┐ ┌────────┐ ┌────────┐       │PATTERN │ │            │ │            │ │            │ │            │
│SWING   │ │<       │ │       >│ │ENTER   │       └────────┘ └────────────┘ └────────────┘ └────────────┘ └────────────┘
└────────┘ └────────┘ └────────┘ └────────┘        KEYBOARD  9 CLEAR        10 CLR AUTO    11 COPY        12 PASTE      
                                                  ┌────────┐ ┌────────────┐ ┌────────────┐ ┌────────────┐ ┌────────────┐
                                                  │PAD MODE│ │            │ │            │ │            │ │            │
- GROUPS ----------------------------------       └────────┘ │            │ │            │ │            │ │            │
┌────────┐ ┌────────┐ ┌────────┐ ┌────────┐        MIX       │            │ │            │ │            │ │            │
│A       │ │B       │ │C       │ │D       │       ┌────────┐ │            │ │            │ │            │ │            │
└────────┘ └────────┘ └────────┘ └────────┘       │NAVIGATE│ │            │ │            │ │            │ │            │
┌────────┐ ┌────────┐ ┌────────┐ ┌────────┐       └────────┘ └────────────┘ └────────────┘ └────────────┘ └────────────┘
│E       │ │F       │ │G       │ │H       │                  5 QUANTIZE     6 QUANT 50%    7 NUDGE <      8 NUDGE >    
└────────┘ └────────┘ └────────┘ └────────┘       ┌────────┐ ┌────────────┐ ┌────────────┐ ┌────────────┐ ┌────────────┐
                                                  │DUPLICAT│ │            │ │            │ │            │ │            │
                                                  └────────┘ │            │ │            │ │            │ │            │
- TRANSPORT -------------------------------        EVENTS    │            │ │            │ │            │ │            │
 LOOP       <STEP         STEP>   REC MODE        ┌────────┐ │            │ │            │ │            │ │            │
┌────────┐ ┌────────┐ ┌────────┐ ┌────────┐       │SELECT  │ │            │ │            │ │            │ │            │
│RESTART │ │<       │ │       >│ │GRID    │       └────────┘ └────────────┘ └────────────┘ └────────────┘ └────────────┘
└────────┘ └────────┘ └────────┘ └────────┘                  1 UNDO         2 REDO         3 COMPARE      4 SPLIT       
 METRO      COUNT-IN                              ┌────────┐ ┌────────────┐ ┌────────────┐ ┌────────────┐ ┌────────────┐
┌────────┐ ┌────────┐ ┌────────┐ ┌────────┐       │SOLO    │ │            │ │            │ │            │ │            │
│PLAY    │ │REC     │ │ERASE   │ │SHIFT   │       └────────┘ │            │ │            │ │            │ │            │
└────────┘ └────────┘ └────────┘ └────────┘        CHOKE     │            │ │            │ │            │ │            │
                                                  ┌────────┐ │            │ │            │ │            │ │            │
                                                  │MUTE    │ │            │ │            │ │            │ │            │
                                                  └────────┘ └────────────┘ └────────────┘ └────────────┘ └────────────┘
```

### Control Functionality

These are all of the controls present on the hardware with their location, label, alternate label and control type. Notably missing are some controls which are not accessible via MIDI mode so cant be used. These include the Top left/right chevron buttons and the transport shift button. The top function buttons and encoders exist in two pages, F1 through F8 and E1 through E8 on page 1 and F9 through F16 and E9 through E16 on page 2. The top left/right chevron buttons are reserved for switching between pages. The shift button in the transport area is reserved for switching the device in and out of MIDI mode. All other controls are configured via a Native Instruments Maschine MK2 Template file (.ncm2 file extension) which defines the MIDI CC and note values and other behaviors and settings for each control. See the full `controller-editor-templates.md` file for details of how to author or edit these files.

| Area   | Label       | Alt Label     | Type    | Functionality                           | Notes                                               |
|--------|-------------|---------------|---------|-----------------------------------------|-----------------------------------------------------|
| Top    | Control     | MIDI          | Button  |                                         |                                                     |
| Top    | Step        | Instance      | Button  |                                         |                                                     |
| Top    | Browse      |               | Button  | focus browser window; press again to hide (shift mode: open the plugin picker; new mode: open FL's Add menu, to add a channel) | illuminated when browser window is focused          |
| Top    | F1          |               | Button  | focus channels window; press again to hide                   | illuminated when channels window is focused         |
| Top    | F2          |               | Button  | focus piano roll window; press again to hide                 | illuminated when piano roll window is focused       |
| Top    | F3          |               | Button  | focus playlist window; press again to hide                   | illuminated when playlist window is focused         |
| Top    | F4          |               | Button  | focus mixer window; press again to hide                      | illuminated when mixer window is focused            |
| Top    | F5          |               | Button  | open the item's context menu in the browser and piano roll, otherwise the focused window's menu |                                                     |
| Top    | F6          |               | Button  | escape                                  |                                                     |
| Top    | F7          |               | Button  | toggle new mode | illuminated while new mode is on |
| Top    | F8          |               | Button  | toggle shift mode                       | illuminated when shift mode is active               |
| Top    | F9          |               | Button  |                                         |                                                     |
| Top    | F10         |               | Button  |                                         |                                                     |
| Top    | F11         |               | Button  |                                         |                                                     |
| Top    | F12         |               | Button  |                                         |                                                     |
| Top    | F13         |               | Button  |                                         |                                                     |
| Top    | F14         |               | Button  |                                         |                                                     |
| Top    | F15         |               | Button  |                                         |                                                     |
| Top    | F16         |               | Button  |                                         |                                                     |
| Top    | Sampling    |               | Button  |                                         |                                                     |
| Top    | All         | Save          | Button  | save project (shift mode)               |                                                     |
| Top    | Auto        |               | Button  |                                         |                                                     |
| Top    | E1          |               | Encoder |                                         |                                                     |
| Top    | E2          |               | Encoder |                                         |                                                     |
| Top    | E3          |               | Encoder |                                         |                                                     |
| Top    | E4          |               | Encoder |                                         |                                                     |
| Top    | E5          |               | Encoder |                                         |                                                     |
| Top    | E6          |               | Encoder |                                         |                                                     |
| Top    | E7          |               | Encoder |                                         |                                                     |
| Top    | E8          |               | Encoder |                                         |                                                     |
| Top    | E9          |               | Encoder |                                         |                                                     |
| Top    | E10         |               | Encoder |                                         |                                                     |
| Top    | E11         |               | Encoder |                                         |                                                     |
| Top    | E12         |               | Encoder |                                         |                                                     |
| Top    | E13         |               | Encoder |                                         |                                                     |
| Top    | E14         |               | Encoder |                                         |                                                     |
| Top    | E15         |               | Encoder |                                         |                                                     |
| Top    | E16         |               | Encoder |                                         |                                                     |
| Master | Volume      |               | Button  | toggle encoder override: the encoder adjusts master volume | illuminated while the override is on |
| Master | Swing       |               | Button  | toggle encoder override: the encoder adjusts master swing | illuminated while the override is on |
| Master | Tempo       |               | Button  | toggle encoder override: the encoder adjusts master tempo | illuminated while the override is on |
| Master | Left        |               | Button  | left (like the left arrow key in the focused window) |                                                     |
| Master | Right       |               | Button  | right (like the right arrow key in the focused window) |                                                     |
| Master | Enter       |               | Button  | enter; in the Channel Rack, open the selected channel's plugin |                                                     |
| Master | Note Repeat | Tap           | Button  |                                         |                                                     |
| Master | Encoder     |               | Encoder | turn: navigate the focused window (up/down, or left/right in the mixer) or an open menu; press: enter (browser, menus), open menu (mixer, playlist, piano roll), open the selected channel's item (right-click) menu (channel rack); a press acts on release, and not at all if the encoder turned while held. Push and turn: select a range of channels (channel rack) or mixer tracks (mixer), starting at the selected channel or current track | Volume / Swing / Tempo overrides take priority for turning, but push and turn in the channel rack or mixer always selects. Needs Encoder Push in Gate mode in the template (reload the updated .ncm2 in Controller Editor) |
| Groups | A -> H      |               | Button  | select pad group: the pads play 16 notes from group × 16 (A 0–15, B 16–31 … H 112–127; middle C is Group D pad 13). While the selected channel is FPC: Group E plays bank A and Group F bank B, in FPC's pad colours; empty pads and the other groups are dark and silent; selecting an FPC jumps to Group E | lit in the selected channel's colour, brightest when selected; starts on Group D; only E and F lit while FPC is selected |
| Transport | Restart     | Loop          | Button  | stop, jump to the start and play        |                                                     |
| Transport | Left        | Step Left     | Button  | move the song position to the previous snap grid line | uses FL's main snap (toolbar); set the Playlist and Piano Roll snap to "Main" so the playhead lands on the same grid |
| Transport | Right       | Step Right    | Button  | move the song position to the next snap grid line | uses FL's main snap (toolbar); set the Playlist and Piano Roll snap to "Main" so the playhead lands on the same grid |
| Transport | Grid        | Rec Mode      | Button  | toggle encoder override: the encoder steps the main snap setting | illuminated while the override is on |
| Transport | Play        | Metro         | Button  | play / pause (shift mode: toggle metronome) | illuminated while playing                           |
| Transport | Rec         | Count-In      | Button  | toggle recording (shift mode: toggle count-in) | illuminated while recording                         |
| Transport | Erase       |               | Button  |                                         |                                                     |
| Pads   | Scene       |               | Button  | switch between pattern and song mode | illuminated in song mode |
| Pads   | Pattern     |               | Button  | toggle encoder override: the encoder jogs through patterns (new mode: start a new pattern) | illuminated while the override is on |
| Pads   | Pad Mode    | Keyboard      | Button  | toggle fixed velocity: pads play at full velocity | illuminated while fixed velocity is on |
| Pads   | Navigate    | Mix           | Button  | toggle encoder override: the encoder jogs between open windows | illuminated while the override is on |
| Pads   | Duplicate   |               | Button  | duplicate (clone) the current pattern   |                                                     |
| Pads   | Select      | Events        | Button  |                                         |                                                     |
| Pads   | Solo        |               | Button  | solo the selected Channel Rack channel (toggle) | lit while the selected channel is soloed       |
| Pads   | Mute        | Choke         | Button  | mute the selected Channel Rack channel (toggle) | lit while the selected channel is muted (also while another channel is soloed) |
| Pads   | Pad 1       | Undo          | Pad     | undo (shift mode)                       | lit orange in shift mode                            |
| Pads   | Pad 2       | Redo          | Pad     | redo (shift mode)                       | lit orange in shift mode                            |
| Pads   | Pad 3       | Compare       | Pad     | toggle the last edit off and on, like Ctrl+Z (shift mode) | lit orange in shift mode          |
| Pads   | Pad 4       | Split         | Pad     | not available: FL's scripting API has no split |                                                     |
| Pads   | Pad 5       | Quantize      | Pad     | quantize the selected channel (shift mode) | lit green in shift mode                             |
| Pads   | Pad 6       | Quantize 50%  | Pad     | not available: FL's scripting API has no quantize strength |                                                     |
| Pads   | Pad 7       | Nudge Left    | Pad     | lower the project tempo 0.1 BPM (shift mode) | lit blue in shift mode                         |
| Pads   | Pad 8       | Nudge Right   | Pad     | raise the project tempo 0.1 BPM (shift mode) | lit blue in shift mode                         |
| Pads   | Pad 9       | Clear         | Pad     | delete (shift mode)                     | lit red in shift mode                               |
| Pads   | Pad 10      | Clear Auto    | Pad     | cut (shift mode); the one pad whose function doesn't match its label | lit yellow in shift mode |
| Pads   | Pad 11      | Copy          | Pad     | copy (shift mode)                       | lit cyan in shift mode                              |
| Pads   | Pad 12      | Paste         | Pad     | paste (shift mode)                      | lit cyan in shift mode                              |
| Pads   | Pad 13      | Semitone Up   | Pad     | raise the selected channel's pitch 1 semitone (shift mode) | lit purple in shift mode |
| Pads   | Pad 14      | Semitone Down | Pad     | lower the selected channel's pitch 1 semitone (shift mode) | lit purple in shift mode |
| Pads   | Pad 15      | Octave Down   | Pad     | lower the selected channel's pitch 1 octave (shift mode); widens the channel's pitch range when needed | lit purple in shift mode |
| Pads   | Pad 16      | Octave Up     | Pad     | raise the selected channel's pitch 1 octave (shift mode); widens the channel's pitch range when needed | lit purple in shift mode |

### Future features/TODO
- shift mode for accessing alt button functionality
- new mode w buttons for adding new patterns/channels, etc
- pads light up on midi out 
- encoder controls active screen + overrides

### Shift and New Modes

F8 toggles shift mode and F7 toggles new mode. Only one of them is on at a time: turning one on turns the other off. The mode's button stays lit while it is on.

- **Shift mode** gives controls their "(shift mode)" function above, such as Browse (plugin picker), Play (metro), Rec (count-in) and the pads (undo, redo, quantize, clear, copy, paste, …). It stays on until F8 is pressed again. In shift mode the pads never play notes.
- **New mode** gives controls their "(new mode)" function: Browse opens FL's Add menu to add a channel, and Pattern starts a new pattern. New mode is one-shot: using a new-mode function turns it off. Controls without a new-mode function keep their normal function, and new mode stays on.

While either mode is on, only its button and the controls with a *working* function in that mode are lit; functions that aren't written yet (or can't be done from an FL script) stay unlit. In shift mode the pads light in colours by function: undo/redo/compare orange, copy/paste cyan, quantize green, nudge (tempo) blue, clear red, cut yellow, transpose (semitone/octave) purple. Every other button goes dim, and the pads and Group buttons without a function go dark. The usual state lights (the focused window, Play/Rec) come back when the mode is turned off. Entering either mode also turns off any active encoder override.

## Akai Fire

The fire features an array of buttons for sequencing drums and instruments and controls largely matching the FL studio channel rack.

Of the 3 controllers, its responsible for 
- channel rack controls

### Hardware Layout Diagram

**TODO**

### Control Functionality

**TODO**

## Novation FLKey 2

The fl key 2 is a compact keyboard with a set of 8 small pan pots.

Of the 3 controllers, its responsible for 
- providing a keyboard to record melodies with
- tweaking and choosing presets

### Hardware Layout Diagram

**TODO**

### Control Functionality

**TODO**

