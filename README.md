# FL Complete MIDI Scripts

This repo contains 3 MIDI scripts for integrating the Akai Fire, Native Instruments Maschine MK2 and Novation FL Keys 2 with FL Studio in one cohesive control surface. Each controller's vendor supplied MIDI scripts try to pack as much functionality as possible into their hardware unit. This means that access to a specific functionality can require putting the controller into a particular state ("pad mode", "sequencer mode", etc), which can be cumbersome and requires keeping a mental model of distinct state spaces for each controller. 
These scripts attempt to solve this by allowing each controller to focus on controlling specific parts of FL studio rather than packing every functionality into every controller. The notable exception where functionality is genuinely meant to be redundant across controllers is transport control.

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
┌────────┐        -------         TAP                        13 SEMI-       14 SEMI+       15 OCTAVE+     16 OCTAVE-
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
└────────┘ └────────┘ └────────┘ └────────┘                  1 UNDO         2 REDO         3 STEP UNDO    4 STEP REDO   
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
| Top    | Browse      |               | Button  | focus browser window                    | illuminated when browser window is focused          |
| Top    | F1          |               | Button  | focus channels window                   | illuminated when channels window is focused         |
| Top    | F2          |               | Button  | focus piano roll window                 | illuminated when piano roll window is focused       |
| Top    | F3          |               | Button  | focus playlist window                   | illuminated when playlist window is focused         |
| Top    | F4          |               | Button  | focus channels mixer window             | illuminated when channels window is focused         |
| Top    | F5          |               | Button  | toggle shift mode                       | illuminated when shift mode is active               |
| Top    | F6          |               | Button  |                                         |                                                     |
| Top    | F7          |               | Button  |                                         |                                                     |
| Top    | F8          |               | Button  |                                         |                                                     |
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
| Master | Volume      |               | Button  | hold + turn encoder to adjust master volume| illuminated while held                           |
| Master | Swing       |               | Button  | hold + turn encoder to adjust master swing| illuminated while held                            |
| Master | Tempo       |               | Button  | hold + turn encoder to adjust master tempo| illuminated while held                            |
| Master | Left        |               | Button  |                                         |                                                     |
| Master | Right       |               | Button  |                                         |                                                     |
| Master | Enter       |               | Button  | enter                                   | depends on focused screen                           |
| Master | Note Repeat | Tap           | Button  |                                         |                                                     |
| Master | Encoder     |               | Encoder | navigate up/down in current screen, press in to enter| depends on focused screen              |
| Groups | A -> H      |               | Button  |                                         |                                                     |
| Pads   | Scene       |               | Button  |                                         |                                                     |
| Pads   | Pattern     |               | Button  |                                         |                                                     |
| Pads   | Pad Mode    | Keyboard      | Button  |                                         |                                                     |
| Pads   | Navigate    | Mix           | Button  |                                         |                                                     |
| Pads   | Duplicate   |               | Button  |                                         |                                                     |
| Pads   | Select      | Events        | Button  |                                         |                                                     |
| Pads   | Solo        |               | Button  |                                         |                                                     |
| Pads   | Mute        | Choke         | Button  |                                         |                                                     |
| Pads   | Pad 1       | Undo          | Pad     | undo (shift mode)                       |                                                     |
| Pads   | Pad 2       | Redo          | Pad     | redo (shift mode)                       |                                                     |
| Pads   | Pad 3       | Step Undo     | Pad     |                                         |                                                     |
| Pads   | Pad 4       | Step Redo     | Pad     |                                         |                                                     |
| Pads   | Pad 5       | Quantize      | Pad     | quantize selection (shift mode)         |                                                     |
| Pads   | Pad 6       | Quantize 50%  | Pad     | undo (shift mode)                       |                                                     |
| Pads   | Pad 7       | Nudge Left    | Pad     |                                         |                                                     |
| Pads   | Pad 8       | Nudge Right   | Pad     |                                         |                                                     |
| Pads   | Pad 9       | Clear         | Pad     | delete                                  |                                                     |
| Pads   | Pad 10      | Clear Auto    | Pad     |                                         |                                                     |
| Pads   | Pad 11      | Copy          | Pad     | copy (shift mode)                       |                                                     |
| Pads   | Pad 12      | Paste         | Pad     | undo (shift mode)                       |                                                     |
| Pads   | Pad 13      | Semitone Down | Pad     | decrease midi offset 1 step (shift mode)|                                                     |
| Pads   | Pad 14      | Semitone Up   | Pad     | increase midi offset 1 step (shift mode)|                                                     |
| Pads   | Pad 15      | Octave Down   | Pad     | decrease midi offset 12 steps (shift mode)|                                                   |
| Pads   | Pad 16      | Octave Up     | Pad     | increase midi offset 12 steps (shift mode)|                                                   |

## Akai Fire

The fire features an array of buttons for sequencing drums and instruments and controls largely matching the FL studio channel rack.

Of the 3 controllers, its responsible for 
- channel rack controls

### Hardware Layout Diagram

**TODO**

### Control Functionality

**TODO**
