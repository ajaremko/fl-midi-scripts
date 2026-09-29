# name=FL Complete Maschine MK2 (Hardware)
"""
Entry script for the MK2 on its own MIDI ports, without the MK2 bridge. Note Repeat isn't
available (it needs the bridge's timing); see device_FLC_MaschineMK2_Bridge.py.
"""

from flc_maschine import diagnostics
from flc_maschine.controller import MaschineMk2

controller = MaschineMk2(bridge=False)


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
