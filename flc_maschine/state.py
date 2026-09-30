"""
Controller state shared by every handler and read by the renderer.

Handlers change it directly; the renderer turns it (plus FL Studio's state) into LEDs after
every event, so a handler never has to touch the LEDs itself.
"""

BASE = "base"
SHIFT = "shift"
NEW = "new"
COLOR = "color"


class ControllerState:
    def __init__(self):
        # Global mode: SHIFT (toggled by F8), NEW (toggled by F7), COLOR (toggled by F12) or None.
        # Only one is on at a time;
        # its binding layer takes priority over the base layer.
        self.mode = None
        # Control id -> the handler that received its press, so the release goes to the same
        # handler even if the active layers changed while the control was held.
        self.held = {}
        # The master encoder's override mode ("VOLUME", "SWING", "TEMPO", "NAVIGATE", "PATTERN"
        # or "GRID"), toggled by those buttons, or None. Entering Shift or New mode clears
        # it. See handlers/encoder.py.
        self.encoder_mode = None
        # Encoder push: held down, and turned while held (a turn cancels the click on release).
        self.push_held = False
        self.push_turned = False
        # A push-and-turn selection drag (handlers/selection.py): the window it selects in (None
        # when no drag is running), the index the range started at, and its moving end.
        self.drag_window = None
        self.drag_anchor = 0
        self.drag_end = 0
        # Pad group A-H (0-7) selected by the Group buttons. It picks the pads' notes (see
        # notes.py); Group D (3) holds middle C, so start there.
        self.pad_group = 3
        # Pad id -> the note sent when it was pressed, so its aftertouch and note-off use the
        # same note even if the group changes while it is held.
        self.sounding = {}
        # Toggled by Pad Mode. While on, pads play at pads.FIXED_VELOCITY however hard they're hit.
        self.fixed_velocity = False
        # Note Repeat mode (bridge mode only), cycled by its button: note_repeat.OFF (0), ON
        # (straight divisions) or TRIPLETS. The MK2 bridge repeats held pads while it isn't OFF.
        self.note_repeat = 0
        # Note Repeat's division: an index into the current mode's note_repeat.RATES, changed by
        # the encoder while Note Repeat is on. Independent of FL's grid snap.
        self.note_repeat_rate = 2  # 1/16 or 1/16T (note_repeat.DEFAULT_RATE)
        # Macros (E9-E16, handlers/macro_knobs.py): each parameter's running value and what FL made
        # of it, keyed by (plugin index, slot, parameter); each plugin's parameter names, looked up
        # once; and what has been logged this session (parameter lists, missing names).
        self.macro_values = {}
        self.macro_params = {}
        self.macro_logged = set()
        # The FPC channel selected at the last render, or None. Selecting a different FPC jumps
        # the pads to Group E.
        self.fpc_channel = None
        # FL commands (midi.FPT_*) waiting for a popup menu to open, and how many OnIdle ticks to
        # keep waiting. See handlers/ui_commands.open_menu_then.
        self.menu_commands = []
        self.menu_wait = 0

    def active_layers(self):
        """Binding layers to search, highest priority first."""
        if self.mode:
            return [self.mode, BASE]
        return [BASE]
