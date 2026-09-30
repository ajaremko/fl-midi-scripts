"""Stand-in for FL Studio's midi module: only the constants the script uses."""

MIDI_NOTEOFF = 0x80
MIDI_NOTEON = 0x90
MIDI_KEYAFTERTOUCH = 0xA0
MIDI_CONTROLCHANGE = 0xB0

GC_Semitone = 1

FPT_Metronome = 110
FPT_Left = 40
FPT_Right = 41
FPT_Up = 42
FPT_Down = 43
FPT_Cut = 50
FPT_Delete = 54
FPT_Insert = 53
FPT_Enter = 80
FPT_Escape = 81
FPT_Menu = 90
FPT_Copy = 51
FPT_Paste = 52
FPT_F8 = 67
FFNEP_DontPromptName = 1
FPT_ItemMenu = 91
FPT_TempoJog = 105
FPT_WindowJog = 59
FPT_PatternJog = 55
FPT_SnapMode = 49
FPT_ShuffleJog = 122
FPT_CountDown = 115
FPT_Save = 92
FPT_SaveNew = 93
FPT_TapTempo = 106
FPT_LoopRecord = 113

REC_Chan_PianoRoll = 15  # the stub's value; FL's own midi module defines the real one
EE_PR = 1

SONGLENGTH_ABSTICKS = 2

SM_Pat = 0

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

# Channel REC event offsets and flags (general.processRECEvent)
REC_Chan_Vol = 0
REC_Chan_Pan = 1
REC_Chan_Pitch = 4
REC_Chan_FXTrack = 8
REC_Chan_GateTime = 9
REC_Chan_TimeOfs = 11
REC_Chan_SwingMix = 12
REC_Chan_OfsPitch = 18
REC_UpdateValue = 1
REC_GetValue = 2
REC_ShowHint = 4
REC_UpdateControl = 32
REC_Control = REC_UpdateValue | REC_UpdateControl
EKRes = 1.0 / 64

PIM_None = 0
CT_Sampler = 0
CT_GenPlug = 2
CT_Layer = 3
CT_AudioClip = 4
