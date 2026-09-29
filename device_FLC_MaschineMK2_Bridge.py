# name=FL Complete Maschine MK2 (Bridge)
"""
Entry script for the MK2 through the MK2 bridge (mk2_bridge/bridge.py) and its loopMIDI ports.
Adds Note Repeat, which the bridge times; see device_FLC_MaschineMK2_Hardware.py for the MK2 on
its own ports.
"""

from flc_maschine import diagnostics
from flc_maschine.controller import MaschineMk2

controller = MaschineMk2(bridge=True)


def OnInit():
    diagnostics.start()
    diagnostics.run("OnInit", controller.on_init)


def OnDeInit():
    diagnostics.run("OnDeInit", controller.on_deinit)


def OnMidiMsg(event):
    diagnostics.run("OnMidiMsg", controller.on_midi_msg, event)


def OnRefresh(flags):
    diagnostics.run("OnRefresh", controller.on_refresh, flags)


def OnIdle():
    diagnostics.run("OnIdle", controller.on_idle)
