#!/usr/bin/env python3
"""Clicks at a point of a wlroots compositor through a virtual pointer.

A headless compositor has no mouse; wlr-virtual-pointer adds one, so
tests/layer_shell_check.py can click where the dial is and see whether the
window below gets the click. Needs python-pywayland and wlr-protocols.

    python3 tests/virtual_pointer.py X Y WIDTH HEIGHT
"""

import sys
import tempfile
import time
from pathlib import Path

PROTOCOL = "/usr/share/wlr-protocols/unstable/wlr-virtual-pointer-unstable-v1.xml"
WAYLAND = "/usr/share/wayland/wayland.xml"
BTN_LEFT = 0x110


def bindings() -> str:
    """Python bindings for the protocol (and wayland.xml, which it uses),
    made by pywayland's scanner as the package "protocols"."""
    from pywayland.scanner import Protocol

    directory = Path(tempfile.mkdtemp(prefix="turnpad-virtual-pointer-"))
    package = directory / "protocols"
    package.mkdir()
    (package / "__init__.py").write_text("")
    protocols = [Protocol.parse_file(path) for path in (PROTOCOL, WAYLAND)]
    imports = {interface.name: protocol.name for protocol in protocols for interface in protocol.interface}
    for protocol in protocols:
        protocol.output(str(package), imports)
    return str(directory)


def main() -> int:
    x, y, width, height = (int(value) for value in sys.argv[1:5])
    sys.path.insert(0, bindings())
    from pywayland.client import Display
    from protocols.wayland import WlSeat
    from protocols.wlr_virtual_pointer_unstable_v1 import ZwlrVirtualPointerManagerV1

    display = Display()
    display.connect()
    found = {}

    def global_added(registry, name, interface, version):
        if interface == ZwlrVirtualPointerManagerV1.name:
            found["manager"] = registry.bind(name, ZwlrVirtualPointerManagerV1, 1)
        elif interface == WlSeat.name:
            found["seat"] = registry.bind(name, WlSeat, 1)

    registry = display.get_registry()
    registry.dispatcher["global"] = global_added
    display.roundtrip()
    pointer = found["manager"].create_virtual_pointer(found.get("seat"))
    display.roundtrip()
    # Clients bind the new pointer first; then move, press and release.
    time.sleep(0.5)
    stamp = int(time.monotonic() * 1000) & 0xFFFFFFFF
    pointer.motion_absolute(stamp, x, y, width, height)
    pointer.frame()
    display.roundtrip()
    time.sleep(0.2)
    for state in (1, 0):
        pointer.button(stamp + 300, BTN_LEFT, state)
        pointer.frame()
        display.roundtrip()
        time.sleep(0.1)
    time.sleep(0.3)
    pointer.destroy()
    display.roundtrip()
    display.disconnect()
    return 0


if __name__ == "__main__":
    sys.exit(main())
