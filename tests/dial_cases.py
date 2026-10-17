"""Dial states shared by the painter comparison (tests/test_live_painter.py)
and the layer-shell test in a container (tests/layer_shell_check.py).

Each case is what the driver sends (an OverlayState tuple and an
OverlayDetails payload) plus the overlay section of config.json, so the same
case can be painted directly or sent over D-Bus to the running dial.
"""

import json

from config.skins import builtin_skins, resolve_skin
from overlay import look

# Tolerance of tools/update_previews.py: a channel difference above
# TOLERANCE is a real change; MIN_PIXELS ignores a few anti-aliased edges.
TOLERANCE = 12
MIN_PIXELS = 25

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


def case_view(case):
    """The view the dial builds from a case's signals and config."""
    appearance = look.load_appearance(case["overlay"])
    state, details = look.new_state(), look.new_details()
    look.apply_overlay_state(state, case["signal"])
    look.merge_details(details, json.dumps(case["details"]))
    skin = resolve_skin(builtin_skins(), look.skin_id(appearance, True))
    return look.make_view(state, details, appearance, skin)


def reference_cases(cases=None):
    """Cases as tests/render_dial_reference.js reads them."""
    entries = []
    for case in CASES if cases is None else cases:
        view = case_view(case)
        entries.append({
            "name": case["name"], "skin": look.skin_id(view["appearance"], True),
            "accent": view["appearance"]["accent"], "appearance": view["appearance"],
            "state": view["state"], "details": view["details"],
        })
    return entries


def changed_pixels(first, second):
    """Pixels of two pictures (paths or PIL images) whose largest channel,
    alpha included, differs by more than TOLERANCE; None when sizes differ."""
    from PIL import Image, ImageChops

    a = first if isinstance(first, Image.Image) else Image.open(first)
    b = second if isinstance(second, Image.Image) else Image.open(second)
    a, b = a.convert("RGBA"), b.convert("RGBA")
    if a.size != b.size:
        return None
    channels = ImageChops.difference(a, b).split()
    largest = channels[0]
    for channel in channels[1:]:
        largest = ImageChops.lighter(largest, channel)
    return largest.point(lambda value: 255 if value > TOLERANCE else 0).histogram()[255]
