"""
MK2 bridge: a small program that sits between the Maschine MK2 and FL Studio.

    MK2 --USB--> bridge --> loopMIDI "MK2 Bridge In"  --> FL (the FL Complete MK2 script)
    MK2 <--USB-- bridge <-- loopMIDI "MK2 Bridge Out" <-- FL (LEDs)

Phase 1 is a plain passthrough: everything the MK2 sends goes to FL unchanged, and everything FL
sends goes to the MK2 unchanged, except MIDI clock and other real-time messages from FL's master
sync, which the MK2 has no use for. Later phases (note repeat) add timing here, where a real timer
is available, instead of in the FL script, which only gets irregular OnIdle calls.

Runs on the Windows machine with FL Studio and the MK2, not in FL's embedded Python. Needs Python 3
with mido and python-rtmidi (pip install -r requirements.txt) and loopMIDI with the two ports above.
FL's MIDI settings must have the MK2's own ports disabled, so the bridge can open them. See the
README's "MK2 bridge" section.

    python bridge.py            run the bridge (Ctrl+C to stop)
    python bridge.py --list     list the MIDI ports mido can see
"""

import argparse
import logging
import sys
import time

DEVICE_NAME = "Maschine MK2"  # substring of the MK2's own port names
TO_FL_NAME = "MK2 Bridge In"  # loopMIDI port FL reads the MK2 from (the script's input)
FROM_FL_NAME = "MK2 Bridge Out"  # loopMIDI port FL sends LEDs to (the script's output)

# Real-time and song position messages from FL's master sync. They mean nothing to the MK2, so
# they are not passed on (phase 2 will use them to follow FL's clock).
FL_ONLY_TYPES = frozenset(["clock", "start", "stop", "continue", "songpos", "active_sensing", "reset"])

log = logging.getLogger("mk2_bridge")


class PortError(Exception):
    pass


def find_port(names, wanted, exclude=()):
    """The one port name containing `wanted` (case-insensitive) and none of `exclude`."""
    wanted_l = wanted.lower()
    excluded = [e.lower() for e in exclude]
    matches = [
        name for name in names
        if wanted_l in name.lower() and not any(e in name.lower() for e in excluded)
    ]
    if len(matches) == 1:
        return matches[0]
    found = "\n  ".join(names) if names else "(none)"
    if not matches:
        raise PortError("no MIDI port matches %r. Ports found:\n  %s" % (wanted, found))
    raise PortError("more than one MIDI port matches %r: %s. Pass a longer name. Ports found:\n  %s"
                    % (wanted, ", ".join(matches), found))


class Bridge:
    """Routes messages between the MK2 and FL. `to_fl` and `to_device` send one message each.

    Each direction runs on its own input port's callback thread and sends to a different output
    port, so the two directions never share a port.
    """

    def __init__(self, to_fl, to_device, trace=False):
        self.to_fl = to_fl
        self.to_device = to_device
        self.trace = trace

    def from_device(self, msg):
        if self.trace:
            log.info("MK2 -> FL  %s", msg)
        self._send(self.to_fl, msg, "FL")

    def from_fl(self, msg):
        if msg.type in FL_ONLY_TYPES:
            return
        if self.trace:
            log.info("FL -> MK2  %s", msg)
        self._send(self.to_device, msg, "MK2")

    def _send(self, send, msg, where):
        # An exception here would be lost on the callback thread; log it and keep going.
        try:
            send(msg)
        except Exception:
            log.exception("could not send %s to %s", msg, where)


def _parse_args(argv):
    parser = argparse.ArgumentParser(description="Pass MIDI between the Maschine MK2 and FL Studio.")
    parser.add_argument("--list", action="store_true", help="list MIDI ports and exit")
    parser.add_argument("--device", default=DEVICE_NAME, help="part of the MK2's port name (default: %(default)s)")
    parser.add_argument("--to-fl", default=TO_FL_NAME, help="loopMIDI port FL reads from (default: %(default)s)")
    parser.add_argument("--from-fl", default=FROM_FL_NAME, help="loopMIDI port FL writes to (default: %(default)s)")
    parser.add_argument("--verbose", action="store_true", help="log every message passed through")
    parser.add_argument("--log", metavar="FILE", help="write the log to FILE (useful with pythonw)")
    return parser.parse_args(argv)


def main(argv=None):
    args = _parse_args(sys.argv[1:] if argv is None else argv)
    logging.basicConfig(
        filename=args.log, level=logging.INFO, format="%(asctime)s %(message)s", datefmt="%H:%M:%S"
    )
    try:
        import mido
    except ImportError:
        log.error("mido is not installed. Run: pip install -r requirements.txt")
        return 1

    inputs, outputs = mido.get_input_names(), mido.get_output_names()
    if args.list:
        print("Inputs:\n  " + "\n  ".join(inputs or ["(none)"]))
        print("Outputs:\n  " + "\n  ".join(outputs or ["(none)"]))
        return 0

    bridge_ports = (args.to_fl, args.from_fl)
    try:
        device_in_name = find_port(inputs, args.device, exclude=bridge_ports)
        device_out_name = find_port(outputs, args.device, exclude=bridge_ports)
        to_fl_name = find_port(outputs, args.to_fl)
        from_fl_name = find_port(inputs, args.from_fl)
    except PortError as error:
        log.error("%s", error)
        return 1

    opened = []
    try:
        # Outputs first, so nothing arrives on an input before it can be passed on.
        device_out = mido.open_output(device_out_name)
        opened.append(device_out)
        to_fl = mido.open_output(to_fl_name)
        opened.append(to_fl)
        bridge = Bridge(to_fl.send, device_out.send, trace=args.verbose)
        opened.append(mido.open_input(device_in_name, callback=bridge.from_device))
        opened.append(mido.open_input(from_fl_name, callback=bridge.from_fl))
    except Exception as error:  # e.g. FL still has the MK2's port open
        log.error("could not open the MIDI ports: %s", error)
        log.error("Is the MK2 disabled in FL's MIDI settings, and is another bridge already running?")
        for port in opened:
            port.close()
        return 1

    log.info("bridge running: %s <-> %s / %s. Ctrl+C to stop.", device_in_name, to_fl_name, from_fl_name)
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        pass
    finally:
        for port in opened:
            port.close()
        log.info("bridge stopped")
    return 0


if __name__ == "__main__":
    sys.exit(main())
