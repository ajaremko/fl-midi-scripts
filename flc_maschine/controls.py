"""
Hardware configuration: every control the Maschine MK2 sends in MIDI mode, and the MIDI message
it sends. This is the only place MIDI numbers appear; everything else refers to controls by id.

The values mirror the Controller Editor template `NI Maschine MK2/FL Complete.ncm2`, which is the
source of truth. After editing the template, update this file to match;
tests/test_template.py fails if the two disagree.

Control ids follow the README's Control Functionality table.
"""

# Control kinds
BUTTON = "button"
ENCODER = "encoder"
PAD = "pad"

# Message types
CC = "cc"
NOTE = "note"

# Button modes, as set per control in the template ("Mode" in Controller Editor)
TRIGGER = "trigger"  # sends on press only
GATE = "gate"  # sends on press and on release
TOGGLE = "toggle"  # alternates on/off values on successive presses

# Encoder modes
ABSOLUTE = "absolute"  # value between min and max
COMP = "comp"  # relative, two's complement: 1 = +1, 127 = -1

# LED types
MONO = "mono"  # single-colour LED, lit by sending the control's own message with 127 / 0
HSB = "hsb"  # colour LED in HSB mode: hue, saturation and brightness sent on channels 0, 1 and 2


class Control:
    __slots__ = ("id", "label", "alt_label", "area", "kind", "msg", "number", "channel", "mode", "led", "template_ref")

    def __init__(self, id, label, area, kind, msg, number, mode, led, template_ref, alt_label="", channel=0):
        self.id = id
        self.label = label
        self.alt_label = alt_label
        self.area = area
        self.kind = kind
        self.msg = msg
        self.number = number
        self.channel = channel
        self.mode = mode
        self.led = led
        # Where the control lives in the .ncm2 file: ("controls", None, xml_id),
        # ("page", page_index, xml_id) or ("pad", pad_page_index, xml_id). Only the tests use it.
        self.template_ref = template_ref

    @property
    def key(self):
        return (self.msg, self.channel, self.number)

    def __repr__(self):
        return "Control(%s)" % self.id


def _button(id, label, area, cc, mode, xml_id, alt_label=""):
    return Control(id, label, area, BUTTON, CC, cc, mode, MONO, ("controls", None, xml_id), alt_label)


def _build():
    controls = [
        # Top
        _button("CONTROL", "Control", "Top", 85, TOGGLE, "Control", "MIDI"),
        _button("STEP", "Step", "Top", 86, TOGGLE, "Step", "Instance"),
        _button("BROWSE", "Browse", "Top", 87, TRIGGER, "Browse"),
        _button("SAMPLING", "Sampling", "Top", 88, TOGGLE, "Sampling"),
        _button("ALL", "All", "Top", 89, TOGGLE, "All", "Save"),
        _button("AUTO", "Auto", "Top", 90, TOGGLE, "AutoWrite"),
        # Master
        _button("VOLUME", "Volume", "Master", 7, TRIGGER, "Volume"),
        _button("SWING", "Swing", "Master", 9, TRIGGER, "Swing"),
        _button("TEMPO", "Tempo", "Master", 3, TRIGGER, "Tempo"),
        _button("MASTER_LEFT", "Left", "Master", 98, TRIGGER, "MasterL"),
        _button("MASTER_RIGHT", "Right", "Master", 99, TRIGGER, "MasterR"),
        _button("ENTER", "Enter", "Master", 100, TRIGGER, "Enter"),
        _button("NOTE_REPEAT", "Note Repeat", "Master", 111, TOGGLE, "NoteRep", "Tap"),
        Control("ENCODER", "Encoder", "Master", ENCODER, CC, 101, COMP, None, ("controls", None, "Dial")),
        _button("ENCODER_PUSH", "Encoder Push", "Master", 102, GATE, "Push"),
        # Transport
        _button("RESTART", "Restart", "Transport", 104, TOGGLE, "Restart", "Loop"),
        _button("STEP_LEFT", "Left", "Transport", 105, TRIGGER, "StepL", "Step Left"),
        _button("STEP_RIGHT", "Right", "Transport", 106, TRIGGER, "StepR", "Step Right"),
        _button("GRID", "Grid", "Transport", 107, TOGGLE, "Grid", "Rec Mode"),
        _button("PLAY", "Play", "Transport", 108, TOGGLE, "Play", "Metro"),
        _button("REC", "Rec", "Transport", 109, TOGGLE, "Rec", "Count-In"),
        _button("ERASE", "Erase", "Transport", 110, TOGGLE, "Erase"),
        # Pads area buttons
        _button("SCENE", "Scene", "Pads", 112, TRIGGER, "Scene"),
        _button("PATTERN", "Pattern", "Pads", 113, TRIGGER, "Pattern"),
        _button("PAD_MODE", "Pad Mode", "Pads", 114, TOGGLE, "PadMode", "Keyboard"),
        _button("NAVIGATE", "Navigate", "Pads", 115, TOGGLE, "Navigate", "Mix"),
        _button("DUPLICATE", "Duplicate", "Pads", 116, TOGGLE, "Duplicate"),
        _button("SELECT", "Select", "Pads", 117, TOGGLE, "Select", "Events"),
        _button("SOLO", "Solo", "Pads", 118, TOGGLE, "Solo"),
        _button("MUTE", "Mute", "Pads", 119, TOGGLE, "Mute", "Choke"),
    ]

    # Groups A-H. <handleGroupControls /> in the template makes these plain CC buttons;
    # switching pad groups is done by the script, not the hardware.
    for letter, cc in zip("ABCDEFGH", (80, 81, 82, 83, 91, 92, 93, 94)):
        controls.append(
            Control("GROUP_" + letter, letter, "Groups", BUTTON, CC, cc, TRIGGER, HSB, ("controls", None, "Group" + letter))
        )

    # F1-F16 and E1-E16: the buttons above and knobs below the displays, on two knob pages.
    # F1-F6 are trigger buttons; the rest are toggle buttons.
    for i in range(16):
        page, slot = divmod(i, 8)
        mode = TRIGGER if i < 6 else TOGGLE
        controls.append(
            Control("F%d" % (i + 1), "F%d" % (i + 1), "Top", BUTTON, CC, 46 + i, mode, MONO, ("page", page, "Button%d" % (slot + 1)))
        )
        controls.append(
            Control("E%d" % (i + 1), "E%d" % (i + 1), "Top", ENCODER, CC, 14 + i, ABSOLUTE, None, ("page", page, "Knob%d" % (slot + 1)))
        )

    # Pads 1-16, numbered from the bottom left as on the hardware. The pads always send
    # Pad Page A's notes; poly aftertouch uses the same note number.
    pad_alt_labels = [
        "Undo", "Redo", "Compare", "Split",
        "Quantize", "Quantize 50%", "Nudge Left", "Nudge Right",
        "Clear", "Clear Auto", "Copy", "Paste",
        "Semitone Up", "Semitone Down", "Octave Down", "Octave Up",
    ]
    for i in range(16):
        controls.append(
            Control(
                "PAD_%d" % (i + 1), "Pad %d" % (i + 1), "Pads", PAD, NOTE, 12 + i, GATE, HSB,
                ("pad", 0, "Pad%d" % (i + 1)), pad_alt_labels[i],
            )
        )

    return controls


ALL_CONTROLS = _build()
BY_ID = {control.id: control for control in ALL_CONTROLS}
BY_KEY = {control.key: control for control in ALL_CONTROLS}
LED_CONTROLS = [control for control in ALL_CONTROLS if control.led is not None]
PADS = [control for control in ALL_CONTROLS if control.kind == PAD]  # PAD_1 ... PAD_16
