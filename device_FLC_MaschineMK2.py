# name=FL Complete Maschine MK2

from flc_maschine import diagnostics
from flc_maschine.controller import MaschineMk2

controller = MaschineMk2()


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
