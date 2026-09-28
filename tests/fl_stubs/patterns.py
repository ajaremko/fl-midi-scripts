"""Stand-in for FL Studio's patterns module. Records the calls the script makes."""

calls = []


def findFirstNextEmptyPat(flags, x=-1, y=-1):
    calls.append(("findFirstNextEmptyPat", flags))
