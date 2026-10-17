#!/usr/bin/env python3
"""On-screen dial for Wayland compositors with layer-shell.

KDE Plasma 6, Hyprland, sway, niri, COSMIC and other wlroots compositors
show the dial through gtk4-layer-shell: a surface on the overlay layer that
never takes keyboard focus, lets every click through and is missing from
Alt-Tab. It does what the GNOME Shell extension does, with the same code
paths in Python: overlay/look.py decides what to show and where,
overlay/visibility.py when, overlay/painter.py paints (three cached layers,
see "Rendering cost" in ARCHITECTURE.md).

Run it in the user's session with the system Python (it needs PyGObject,
GTK 4 and gtk4-layer-shell's introspection data):

    python3 /opt/asus-turnpad/overlay/layer_shell.py [--output NAME]
    python3 -m overlay.layer_shell            # from the program directory

gtk4-layer-shell must be loaded before libwayland-client, so the program
restarts itself once with LD_PRELOAD set; service files need nothing
special. Exit status 3 means the desktop has no layer-shell (GNOME uses the
extension, X11 has no layers); a service should not restart then.

Which screen: Wayland does not tell clients where the pointer is, so the
dial lets the compositor choose, and compositors put a new layer surface on
the focused output, where the user works. It hides between touches, so
every touch picks again. --output pins it to one connector (e.g. eDP-1).
"""

from __future__ import annotations

import argparse
import ctypes.util
import glob
import os
import signal
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# Set when the program restarted itself with the library preloaded, so a
# library that cannot be preloaded does not restart it again and again.
PRELOADED = "TURNPAD_LAYER_SHELL_PRELOADED"
EXIT_UNSUPPORTED = 3


def log(message: str) -> None:
    print(f"turnpad-dial: {message}", file=sys.stderr, flush=True)


# --- loading gtk4-layer-shell first ----------------------------------------------

def find_library() -> str | None:
    """gtk4-layer-shell's shared library, as LD_PRELOAD takes it."""
    name = ctypes.util.find_library("gtk4-layer-shell")
    if name:
        return name
    # find_library() needs ldconfig, which is not on every PATH.
    for pattern in ("/usr/lib/libgtk4-layer-shell.so*", "/usr/lib64/libgtk4-layer-shell.so*",
                    "/usr/lib/*-linux-gnu/libgtk4-layer-shell.so*", "/usr/local/lib*/libgtk4-layer-shell.so*"):
        found = sorted(glob.glob(pattern))
        if found:
            return found[0]
    return None


def preload_command(environ, library: str | None, argv: list[str]):
    """(argv, environment) to restart with the library preloaded, or None
    when it is loaded already, was tried or is not installed."""
    preload = environ.get("LD_PRELOAD", "")
    if not library or environ.get(PRELOADED) or "gtk4-layer-shell" in preload:
        return None
    environment = dict(environ)
    environment["LD_PRELOAD"] = f"{library} {preload}".strip()
    environment[PRELOADED] = "1"
    return argv, environment


def ensure_preloaded() -> None:
    command = preload_command(os.environ, find_library(), list(sys.orig_argv))
    if command:
        argv, environment = command
        os.execve(sys.executable, argv, environment)


# --- the dial ------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Turnpad on-screen dial for layer-shell compositors")
    parser.add_argument("--output", metavar="NAME", help="always show on this output (connector, e.g. eDP-1)")
    args = parser.parse_args(argv)

    if not os.environ.get("WAYLAND_DISPLAY"):
        log("needs a Wayland session (WAYLAND_DISPLAY is not set); X11 has no layer-shell")
        return EXIT_UNSUPPORTED
    ensure_preloaded()

    import gi

    gi.require_version("Gdk", "4.0")
    gi.require_version("Gtk", "4.0")
    try:
        gi.require_version("Gtk4LayerShell", "1.0")
    except ValueError:
        log("gtk4-layer-shell is not installed (package gtk4-layer-shell or libgtk4-layer-shell0)")
        return EXIT_UNSUPPORTED
    from gi.repository import GLib, Gtk, Gtk4LayerShell

    if not Gtk.init_check():
        log("cannot open the display")
        return 1
    if not Gtk4LayerShell.is_supported():
        log("this compositor has no layer-shell; on GNOME the Turnpad Shell extension shows the dial")
        return EXIT_UNSUPPORTED

    from overlay.frontend import DialFrontend

    loop = GLib.MainLoop()
    frontend = DialFrontend(output=args.output)
    for number in (signal.SIGINT, signal.SIGTERM):
        GLib.unix_signal_add(GLib.PRIORITY_DEFAULT, number, lambda: (loop.quit(), GLib.SOURCE_REMOVE)[1])
    frontend.start()
    log(f"running on {os.environ.get('WAYLAND_DISPLAY')}")
    try:
        loop.run()
    finally:
        frontend.stop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
