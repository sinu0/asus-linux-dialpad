"""Dial states shared by the painter comparison (tests/test_live_painter.py)
and the layer-shell test in a container (tests/layer_shell_check.py).

Each case is what the driver sends (an OverlayState tuple and an
OverlayDetails payload) plus the overlay section of config.json, so the same
case can be painted directly or sent over D-Bus to the running dial.
"""

MENU = ["Volume", "Brightness", "Scroll", "Zoom", "Undo / Redo", "Media"]
COLORS = ["#6cb6ff", "#f4c95d", "#9ad17b", "#e7b98d", "#c99bff", "#ff8f8f"]
NO_TITLES = [""] * len(MENU)


def signal(title="", titles=None, value=0, angle=0.0, unit="", pressed=False, progress=False, touching=True,
           enabled=True):
    """OverlayState(bsasasidsbbb) as a tuple."""
    titles = MENU if titles is None else titles
    return (enabled, title, titles, [""] * len(titles), value, angle, unit, pressed, progress, touching)


CASES = [
    {
        "name": "menu-hover",
        "overlay": {"skin": "glass"},
        "signal": signal("Zoom"),
        "details": {"profile": "Default", "colors": COLORS, "pointer": 228},
    },
    {
        "name": "volume",
        "overlay": {"skin": "glass"},
        "signal": signal("Volume", NO_TITLES, value=64, unit="%"),
        "details": {"profile": "Default", "colors": COLORS, "color": "#6cb6ff", "pointer": 118,
                    "hints": {"ccw": "Quieter", "cw": "Louder", "center": "Mute"}},
    },
    {
        "name": "zoom-pressed",
        "overlay": {"skin": "midnight"},
        "signal": signal("Zoom", NO_TITLES, pressed=True),
        "details": {"profile": "darktable", "colors": COLORS, "color": "#e7b98d", "pointer": 292,
                    "hints": {"ccw": "Zoom out", "cw": "Zoom in", "center": "Fit image"}},
    },
    {
        "name": "undo-progress",
        "overlay": {"skin": "proart"},
        "signal": signal("Undo / Redo", NO_TITLES, value=-40, angle=30.0, progress=True),
        "details": {"profile": "Krita", "mode": "single", "colors": COLORS, "color": "#c99bff", "pointer": 30,
                    "hints": {"ccw": "Undo", "cw": "Redo"}},
    },
    {
        "name": "segments-menu",
        "overlay": {"skin": "classic", "scale": 1.3},
        "signal": signal("Menu"),
        "details": {"profile": "Inkscape", "colors": COLORS, "pointer": -1},
    },
    {
        "name": "frost-small",
        "overlay": {"skin": "frost", "scale": 0.6, "show_hints": False, "show_pointer": False},
        "signal": signal("Brightness", NO_TITLES, value=30, unit="%"),
        "details": {"profile": "Default", "colors": COLORS, "color": "#f4c95d", "pointer": 200,
                    "hints": {"ccw": "Darker", "cw": "Brighter"}},
    },
]
