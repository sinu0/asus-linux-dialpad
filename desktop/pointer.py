"""Where the mouse pointer is, for the dial's position "pointer".

Wayland clients only see the pointer over their own windows, and the
layer-shell dial has no input region at all, so the position comes from the
compositor where it tells it:

- Hyprland: "cursorpos" on its IPC socket, in global logical pixels.
- sway, niri, KDE Plasma (KWin shows the cursor only to its scripts),
  COSMIC: no way to ask; position() returns None and the dial falls back
  to "lower".

The GNOME extension asks the Shell itself (global.get_pointer()). The
frontend calls position() only when a fully hidden dial is about to show,
never per touch frame; the socket answers within a millisecond and gives up
after TIMEOUT_S, so the GTK main loop is not held up for long.
"""

from __future__ import annotations

import json
import os
import socket
from pathlib import Path

TIMEOUT_S = 0.05


def _hyprland_socket() -> Path | None:
    signature = os.environ.get("HYPRLAND_INSTANCE_SIGNATURE")
    if not signature:
        return None
    runtime = os.environ.get("XDG_RUNTIME_DIR") or f"/run/user/{os.getuid()}"
    # Hyprland 0.40 moved the socket from /tmp to the runtime directory.
    for base in (Path(runtime) / "hypr", Path("/tmp/hypr")):
        path = base / signature / ".socket.sock"
        if path.exists():
            return path
    return None


def _hyprland() -> tuple[float, float] | None:
    path = _hyprland_socket()
    if path is None:
        return None
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as connection:
        connection.settimeout(TIMEOUT_S)
        connection.connect(str(path))
        connection.sendall(b"j/cursorpos")
        reply = b""
        while chunk := connection.recv(4096):
            reply += chunk
    answer = json.loads(reply)
    return float(answer["x"]), float(answer["y"])


BACKENDS = (_hyprland,)


def position() -> tuple[float, float] | None:
    """The pointer in global logical pixels, or None where the compositor
    does not tell."""
    for backend in BACKENDS:
        try:
            found = backend()
        except (OSError, ValueError, KeyError, TypeError):
            continue
        if found is not None:
            return found
    return None
