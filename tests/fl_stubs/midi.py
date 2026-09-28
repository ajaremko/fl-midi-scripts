"""Stand-in for FL Studio's midi module: only the constants the script uses."""

MIDI_NOTEOFF = 0x80
MIDI_NOTEON = 0x90
MIDI_KEYAFTERTOUCH = 0xA0
MIDI_CONTROLCHANGE = 0xB0

GC_Semitone = 1

FPT_Metronome = 110
FPT_CountDown = 115

SONGLENGTH_ABSTICKS = 2

Snap_Line = 0
Snap_Cell = 1
Snap_None = 3
Snap_SixthStep = 4
Snap_FourthStep = 5
Snap_ThirdStep = 6
Snap_HalfStep = 7
Snap_Step = 8
Snap_SixthBeat = 9
Snap_FourthBeat = 10
Snap_ThirdBeat = 11
Snap_HalfBeat = 12
Snap_Beat = 13
Snap_Bar = 14

widMixer = 0
widChannelRack = 1
widPlaylist = 2
widPianoRoll = 3
widBrowser = 4
