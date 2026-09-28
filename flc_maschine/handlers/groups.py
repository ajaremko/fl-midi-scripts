"""
Group A-H buttons: select which pad group the pads belong to.
"""

from .common import on_press


def select(index):
    @on_press
    def handler(controller, ev):
        controller.state.pad_group = index

    return handler
