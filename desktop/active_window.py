"""Which application has focus, one backend per desktop.

The driver asks ActiveWindow.query() for (binary, title) of the focused
window to pick the application profile. Each backend is a function that
returns that pair or raises; the first backend that answers wins.

Adding a desktop: write a function taking a Context, decorate it with
@backend(name, sessions) and keep it cheap. Backends that fail are skipped
after max_failures attempts so a missing tool costs one try, not one per
frame. On GNOME the Shell extension also pushes the focused app over D-Bus
(SetActiveApplication), which takes precedence over polling.
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
from dataclasses import dataclass, field
from typing import Callable

from config.identity import SLUG

log = logging.getLogger(SLUG)

WindowInfo = tuple  # (binary path or None, title or None)


@dataclass
class Context:
    """What backends may need from the driver."""

    session_type: str | None
    # Returns the driver's current Xlib display (it is reopened when the
    # keyboard layout changes), or None.
    x11_display: Callable[[], object] = lambda: None
    qdbus: str | None = field(default_factory=lambda: shutil.which("qdbus") or shutil.which("qdbus6"))


@dataclass
class Backend:
    name: str
    sessions: tuple[str, ...]
    query: Callable[[Context], WindowInfo]
    # None retries forever (X11 errors are transient).
    max_failures: int | None = 1


BACKENDS: list[Backend] = []


def backend(name: str, sessions: tuple[str, ...], max_failures: int | None = 1):
    def register(function):
        BACKENDS.append(Backend(name, sessions, function, max_failures))
        return function

    return register


def binary_from_pid(pid):
    try:
        return os.readlink(f"/proc/{pid}/exe")
    except Exception:
        return None


def _output(command):
    return subprocess.check_output(command, stderr=subprocess.DEVNULL).decode().strip()


# --- backends, tried in this order -----------------------------------------


@backend("x11", ("x11",), max_failures=None)
def x11(context: Context) -> WindowInfo:
    import Xlib.X

    display = context.x11_display()
    if display is None:
        return None, None
    root = display.screen().root
    window_id = root.get_full_property(display.intern_atom("_NET_ACTIVE_WINDOW"), Xlib.X.AnyPropertyType).value[0]
    window = display.create_resource_object("window", window_id)
    name = window.get_full_property(display.intern_atom("_NET_WM_NAME"), Xlib.X.AnyPropertyType)
    title = name.value.decode() if name else None
    pid = window.get_full_property(display.intern_atom("_NET_WM_PID"), Xlib.X.AnyPropertyType)
    return (binary_from_pid(pid.value[0]) if pid else None), title


@backend("kde", ("wayland",))
def kde(context: Context) -> WindowInfo:
    if not context.qdbus:
        raise RuntimeError("qdbus not found")
    window_id = _output([context.qdbus, "org.kde.KWin", "/KWin", "org.kde.KWin.activeWindow"])
    path = f"/org/kde/KWin/Window/{window_id}"
    title = _output([context.qdbus, "org.kde.KWin", path, "org.kde.KWin.Window.caption"])
    pid = _output([context.qdbus, "org.kde.KWin", path, "org.kde.KWin.Window.pid"])
    return binary_from_pid(pid), title


@backend("gnome", ("wayland",))
def gnome(_context: Context) -> WindowInfo:
    import dbus

    shell = dbus.SessionBus().get_object("org.gnome.Shell", "/org/gnome/Shell")
    return None, shell.Get("org.gnome.Shell", "focusWindow").get("title", None)


@backend("niri", ("wayland",))
def niri(_context: Context) -> WindowInfo:
    window = json.loads(_output(["niri", "msg", "--json", "focused-window"]))
    pid = window.get("pid")
    return (binary_from_pid(pid) if pid else None), window.get("title")


@backend("sway", ("wayland",))
def sway(_context: Context) -> WindowInfo:
    def focused(node):
        if node.get("focused"):
            return node
        for child in node.get("nodes", []) + node.get("floating_nodes", []):
            found = focused(child)
            if found:
                return found
        return None

    node = focused(json.loads(_output(["swaymsg", "-t", "get_tree"])))
    if not node:
        return None, None
    pid = node.get("pid")
    return (binary_from_pid(pid) if pid else None), node.get("name")


@backend("hyprland", ("wayland",))
def hyprland(_context: Context) -> WindowInfo:
    window = json.loads(_output(["hyprctl", "activewindow", "-j"]))
    pid = window.get("pid")
    return (binary_from_pid(pid) if pid else None), window.get("title")


class ActiveWindow:
    def __init__(self, context: Context, backends: list[Backend] | None = None):
        self.context = context
        self.backends = list(BACKENDS if backends is None else backends)
        self.failures = {item.name: 0 for item in self.backends}

    def query(self) -> WindowInfo:
        # As before the split: X11 only with an open display, everything
        # else is treated as Wayland.
        x11 = self.context.session_type == "x11" and self.context.x11_display() is not None
        session = "x11" if x11 else "wayland"
        for item in self.backends:
            if session not in item.sessions:
                continue
            if item.max_failures is not None and self.failures[item.name] >= item.max_failures:
                continue
            try:
                binary, title = item.query(self.context)
            except Exception as error:
                self.failures[item.name] += 1
                log.debug("%s window lookup failed (%d): %s", item.name, self.failures[item.name], error)
                continue
            if binary or title:
                return binary, title
        log.debug("No desktop backend reported the focused window.")
        return None, None
