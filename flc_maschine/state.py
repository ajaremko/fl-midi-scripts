"""
Controller state shared by every handler and read by the renderer.

Handlers change it directly; the renderer turns it (plus FL Studio's state) into LEDs after
every event, so a handler never has to touch the LEDs itself.
"""

BASE = "base"
SHIFT = "shift"


class ControllerState:
    def __init__(self):
        # Latched by F8. While on, the shift binding layer takes priority over the base layer.
        self.shift = False
        # Control id -> the handler that received its press, so the release goes to the same
        # handler even if the active layers changed while the control was held.
        self.held = {}
        # The master encoder's override mode ("VOLUME", "SWING" or "TEMPO"), toggled by those
        # buttons, or None. See handlers/encoder.py.
        self.encoder_mode = None
        # Pad group A-H (0-7) selected by the Group buttons. It picks the pads' notes (see
        # notes.py); Group D (3) holds middle C, so start there.
        self.pad_group = 3
        # Pad id -> the note sent when it was pressed, so its aftertouch and note-off use the
        # same note even if the group changes while it is held.
        self.sounding = {}
        # The FPC channel selected at the last render, or None. Selecting a different FPC jumps
        # the pads to Group E.
        self.fpc_channel = None

    def active_layers(self):
        """Binding layers to search, highest priority first."""
        if self.shift:
            return [SHIFT, BASE]
        return [BASE]
