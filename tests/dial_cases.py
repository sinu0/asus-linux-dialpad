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
# The monitor the reference pictures place the dial and a group's list on.
MONITOR = {"width": 1920, "height": 1080}


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
    # Groups: "Brightness" (sector 1, right half) and "Undo / Redo" (sector
    # 4, left half) stand for groups whose list is open beside the dial.
    {
        "name": "group-list",
        "overlay": {"skin": "glass"},
        "signal": signal("Opacity"),
        "details": {"profile": "Krita", "colors": COLORS, "pointer": 64,
                    "submenu": {"title": "Brightness", "index": 1, "items": ["Size", "Opacity", "Flow"],
                                "icons": ["", "", ""], "colors": ["#6cb6ff", "#f4c95d", "#9ad17b"],
                                "selected": 1}},
    },
    {
        "name": "group-list-long",
        "overlay": {"skin": "classic", "scale": 1.3, "show_hints": False},
        "signal": signal("Item 9"),
        "details": {"profile": "Inkscape", "colors": COLORS, "pointer": 250,
                    "submenu": {"title": "Undo / Redo", "index": 4, "items": [f"Item {n}" for n in range(12)],
                                "icons": ["", "", "edit-copy-symbolic"], "colors": COLORS, "selected": 9}},
    },
    {
        "name": "group-function",
        "overlay": {"skin": "midnight"},
        "signal": signal("Opacity", NO_TITLES, value=40, unit="%"),
        "details": {"profile": "Krita", "colors": COLORS, "color": "#f4c95d", "pointer": 150, "parent": "Brightness",
                    "icon": "", "hints": {"ccw": "Less", "cw": "More", "center": "Reset"}},
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


def reference_cases(cases=None, monitor=None):
    """Cases as tests/render_dial_reference.js reads them; monitor: logical
    {"width", "height"} that places a group's list (default MONITOR)."""
    entries = []
    for case in CASES if cases is None else cases:
        view = case_view(case)
        entries.append({
            "name": case["name"], "skin": look.skin_id(view["appearance"], True),
            "accent": view["appearance"]["accent"], "appearance": view["appearance"],
            "state": view["state"], "details": view["details"], "monitor": monitor or MONITOR,
        })
    return entries


def dial_placement(view, monitor=None):
    """Where the dial of a case goes on a monitor (logical pixels)."""
    rule = look.effective_look(view["appearance"], view["details"].get("look"))
    return look.overlay_placement(monitor or MONITOR, view["appearance"]["scale"], rule["position"], rule["custom"])


def list_placement(view, monitor=None):
    """Where a case's group list goes beside its dial, or None
    (_updateSubmenu() in extension.js)."""
    submenu = look.open_submenu(view)
    if not submenu:
        return None
    appearance = view["appearance"]
    size = look.submenu_size(len(submenu["items"]), appearance["show_hints"])
    return look.submenu_placement(monitor or MONITOR, dial_placement(view, monitor), appearance["scale"], size,
                                  submenu["preferRight"])


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
