"""Stand-in for FL Studio's device module. Records every message sent to the controller."""

sent = []
assigned = True


def isAssigned():
    return assigned


def getPortNumber():
    return 0


def midiOutMsg(message):
    sent.append(message)


def reset():
    del sent[:]
