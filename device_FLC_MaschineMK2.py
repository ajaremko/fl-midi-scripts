# name=FL Complete Maschine MK2

from flc_maschine.controller import MaschineMk2

controller = MaschineMk2()


def OnInit():
    controller.on_init()


def OnDeInit():
    controller.on_deinit()


def OnMidiMsg(event):
    controller.on_midi_msg(event)


def OnRefresh(flags):
    controller.on_refresh(flags)


def OnIdle():
    controller.on_idle()
