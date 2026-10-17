#!/usr/bin/env python3
"""Clicks and types on KWin through its fake input protocol.

KWin has no wlr-virtual-pointer or virtual keyboard; org_kde_kwin_fake_input
gives tests/layer_shell_check.py a mouse and a keyboard on headless KWin
(started with KWIN_WAYLAND_NO_PERMISSION_CHECKS=1). Needs python-pywayland
and plasma-wayland-protocols.

    python3 tests/kwin_fake_input.py click X Y     # logical pixels
    python3 tests/kwin_fake_input.py key CODE      # evdev key code (KEY_Q = 16)
"""

import sys
import time

from virtual_pointer import BTN_LEFT, bindings

PROTOCOL = "/usr/share/plasma-wayland-protocols/fake-input.xml"


def main() -> int:
    action, *values = sys.argv[1:]
    sys.path.insert(0, bindings(PROTOCOL))
    from pywayland.client import Display
    from protocols.fake_input import OrgKdeKwinFakeInput

    display = Display()
    display.connect()
    found = {}

    def global_added(registry, name, interface, version):
        if interface == OrgKdeKwinFakeInput.name:
            found["input"] = registry.bind(name, OrgKdeKwinFakeInput, min(version, 4))

    registry = display.get_registry()
    registry.dispatcher["global"] = global_added
    display.roundtrip()
    fake = found["input"]
    fake.authenticate("Turnpad test", "clicks and keys for the layer-shell dial test")
    display.roundtrip()
    if action == "click":
        x, y = (float(value) for value in values)
        fake.pointer_motion_absolute(x, y)
        display.roundtrip()
        time.sleep(0.2)
        for state in (1, 0):
            fake.button(BTN_LEFT, state)
            display.roundtrip()
            time.sleep(0.1)
    elif action == "key":
        for state in (1, 0):
            fake.keyboard_key(int(values[0]), state)
            display.roundtrip()
            time.sleep(0.05)
    else:
        raise SystemExit(f"unknown action {action}")
    time.sleep(0.3)
    display.disconnect()
    return 0


if __name__ == "__main__":
    sys.exit(main())
