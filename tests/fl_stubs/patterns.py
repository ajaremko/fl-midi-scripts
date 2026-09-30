"""Stand-in for FL Studio's patterns module. Records the calls the script makes."""

calls = []
current = 1  # patternNumber()
selected = set()  # patterns selected in the Picker


def findFirstNextEmptyPat(flags, x=-1, y=-1):
    calls.append(("findFirstNextEmptyPat", flags))


def patternNumber():
    return current


def isPatternSelected(index):
    return 1 if index in selected else 0


def jumpToPattern(index):
    calls.append(("jumpToPattern", index))


def clonePattern(index=-1, destIndex=-1):
    calls.append(("clonePattern",))


length = 16  # getPatternLength() of every pattern, in steps


def getPatternLength(index):
    return length

names = {}  # pattern index -> name (default "Pattern N")


def getPatternName(index):
    return names.get(index, "Pattern %d" % index)


def setPatternLength(index, steps):
    global length
    calls.append(("setPatternLength", index, steps))
    length = steps
