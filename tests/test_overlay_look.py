"""overlay/look.py decides like the GNOME extension.

The same inputs go through the JavaScript originals in dial.js (run in gjs)
and their Python twins; the results must be equal. Constants of dial.js and
extension.js are read from the source.
"""

import itertools
import json
import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from config.skins import builtin_skins, resolve_skin
from overlay import look

ROOT = Path(__file__).resolve().parents[1]
DIAL_JS = ROOT / "gnome" / "extension" / "dial.js"
EXTENSION_JS = ROOT / "gnome" / "extension" / "extension.js"

MONITORS = [(1920, 1080), (1440, 900), (2560, 1600), (1280, 720), (3440, 1440), (800, 600), (1707, 1067)]
SCALES = [0.6, 0.85, 1.0, 1.25, 1.6]
POSITIONS = ["center", "lower", "bottom", "top", "custom", "pointer", "side", None]
CUSTOM = [[0, 0], [0.5, 0.5], [1, 1], [0.25, 0.75], [0.123, 0.987]]
SIDES = ["below-right", "below-left", "above-right", "above-left", "right", "left", "above", "below", "nope"]
GAPS = [0, 24, 37.5, 400]
# Pointers as fractions of the monitor: corners, edges, centre and odd spots.
POINTER_SPOTS = [(0, 0), (1, 0), (0, 1), (0.9995, 0.9995), (0.5, 0.5), (0.5, 0), (0, 0.5), (1, 0.5), (0.5, 1),
                 (0.31, 0.77), (0.123, 0.456)]


def spot(w, h, fx, fy):
    """A pointer on a monitor: whole pixels, or fractional ones for odd spots."""
    return [w * fx, h * fy] if (fx, fy) == (0.123, 0.456) else [round(w * fx), round(h * fy)]

LOOKS = [
    {},
    None,
    {"position": "custom", "custom_x": 0.9, "visibility": "fade", "fade_opacity": 50},
    {"position": "side", "custom_x": 7, "visibility": "loud", "fade_opacity": -1},
    {"position": "top", "custom_x": True, "custom_y": "0.3", "visibility": "pill", "fade_opacity": 100},
    {"custom_y": 0, "fade_opacity": 0, "visibility": ["pill"]},
    {"position": "pointer", "pointer_side": "left", "pointer_gap": 0, "visibility": "pill"},
    {"position": "pointer", "pointer_side": "above", "pointer_gap": 400},
    {"position": "pointer", "pointer_side": "sideways", "pointer_gap": 401, "visibility": "pill"},
    {"pointer_side": ["left"], "pointer_gap": "24", "visibility": "pill"},
    {"pointer_side": "above-left", "pointer_gap": True},
]
APPEARANCES = [
    {"position": "lower", "custom_x": 0.5, "custom_y": 0.5, "visibility": "full", "fade_opacity": 35},
    {"position": "bottom", "custom_x": 0.2, "custom_y": 0.8, "visibility": "pill", "fade_opacity": 70},
    {"position": "pointer", "pointer_side": "right", "pointer_gap": 60, "visibility": "pill"},
    {},
]

MENU = ["Volume", "Brightness", "", "Zoom", "Undo / Redo"]
COLORS = ["#6cb6ff", "f4c95d", "bad", "#e7b98d", None]


def state(title, titles, **extra):
    return {
        "enabled": True, "title": title, "titles": titles, "icons": ["", "", "", "my-zoom", ""][:len(titles)],
        "menuTitles": MENU, "menuIcons": ["", "/nonexistent.svg", "", "my-zoom", ""],
        "value": 64, "valueAngleStart": 0, "unit": "%", "centerPressed": False,
        "valueShowOnlyProgress": False, "touching": True, **extra,
    }


def views():
    skin = resolve_skin(builtin_skins(), "glass")
    states = [
        state("Zoom", MENU),
        state("Menu", MENU),
        state("", MENU),
        state("Volume", ["", "", "", "", ""]),
        state("Volume", [], unit=""),
        state("Undo / Redo", [], valueShowOnlyProgress=True, value=-30),
        state("Unknown", MENU),
        state("Brightness", [], touching=False),
        state("Zoom", ["A", "B", "C", "D", "E", "F", "G", "H", "Zoom"]),
    ]
    details = [
        {"profile": "Krita", "colors": COLORS, "color": "#ff0000", "pointer": 228},
        {"profile": "", "colors": [], "color": "", "pointer": -1},
        {"colors": COLORS, "pointer": 0},
        {"profile": "darktable", "colors": COLORS, "color": "nope", "pointer": 359.5},
    ]
    result = []
    for index, (st, de) in enumerate(itertools.product(states, details)):
        appearance = {"scale": SCALES[index % len(SCALES)], "show_pointer": index % 3 != 0}
        result.append({"state": st, "details": de, "appearance": appearance,
                       "accent": [0.9, 0.7, 0.5, 1], "skin": skin})
    return result


SCRIPT = """
import GLib from 'gi://GLib';
import { effectiveLook, iconLayout, overlayPlacement, parseColor, pillContent, pillPlacement,
         pointerPlacement, isSelectedMode, segmentState, iconNameFor } from '%s';
const input = JSON.parse(new TextDecoder().decode(GLib.file_get_contents(ARGV[0])[1]));
const out = {};
out.placements = input.placements.map(([w, h, scale, position, custom, ...near]) =>
    overlayPlacement({ width: w, height: h }, scale, position, custom, ...near));
out.looks = input.looks.map(([appearance, look]) => effectiveLook(appearance, look));
out.pills = input.pills.map(([w, h, scale, look, pw, ph, pointer]) =>
    pillPlacement({ width: w, height: h }, scale, look, pw, ph, pointer));
out.views = input.views.map(view => ({
    pill: pillContent(view),
    icons: iconLayout(view),
    pointer: pointerPlacement(view),
    selected: isSelectedMode(view.state),
    segments: segmentState(view.state),
}));
out.colors = input.colors.map(text => parseColor(text, [9, 9, 9, 9]));
out.iconNames = input.titles.map(iconNameFor);
print(JSON.stringify(out));
"""


def normal(value):
    """JSON-comparable: tuples become lists, floats are rounded, -0 is 0."""
    if isinstance(value, dict):
        return {key: normal(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [normal(item) for item in value]
    if isinstance(value, float):
        rounded = round(value, 9)
        return 0 if rounded == 0 else (int(rounded) if rounded.is_integer() else rounded)
    return value


@unittest.skipUnless(shutil.which("gjs"), "gjs is not installed")
class LookTwinsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.input = {
            "placements": [
                [w, h, scale, position, custom]
                for (w, h), scale, position, custom in itertools.product(MONITORS, SCALES, POSITIONS, CUSTOM)
            ] + [
                [w, h, scale, position, None, spot(w, h, *at), side, gap]
                for (w, h), scale, position, at, side, gap in itertools.product(
                    MONITORS, SCALES, ["pointer", "lower"], POINTER_SPOTS, SIDES, GAPS)
            ] + [
                # Without a pointer "pointer" is "lower".
                [w, h, scale, "pointer", None, None, "left", 24] for (w, h), scale in itertools.product(MONITORS, SCALES)
            ],
            "looks": [[appearance, rule] for appearance in APPEARANCES for rule in LOOKS],
            "pills": [
                [w, h, scale, look.effective_look(appearance, rule), pw, ph, pointer and spot(w, h, *pointer)]
                for (w, h), scale, appearance, rule, (pw, ph), pointer in itertools.product(
                    MONITORS[:3], SCALES[::2], APPEARANCES, LOOKS, [(200, 40), (151, 37), (2000, 50)],
                    [None, (0, 0), (0.5, 0.5), (1, 1), (0.31, 0.77)])
            ],
            "views": views(),
            "colors": ["#e7b98d", "E7B98D", " #102030 ", "#12345", "#1234567", None, 7, "#gggggg"],
            "titles": ["Volume", "Brush size", "Lock screen", "Terminal", "", "Something else"],
        }
        with tempfile.NamedTemporaryFile("w", suffix=".js") as script, \
                tempfile.NamedTemporaryFile("w", suffix=".json") as data:
            script.write(SCRIPT % DIAL_JS.as_uri())
            script.flush()
            json.dump(cls.input, data)
            data.flush()
            result = subprocess.run(["gjs", "-m", script.name, data.name],
                                    capture_output=True, text=True, check=True, timeout=60)
        cls.js = json.loads(result.stdout.strip().splitlines()[-1])

    def test_overlay_placement(self):
        for args, expected in zip(self.input["placements"], self.js["placements"]):
            w, h, scale, position, custom, *near = args
            with self.subTest(args=args):
                self.assertEqual(look.overlay_placement({"width": w, "height": h}, scale, position, custom, *near),
                                 expected)

    def test_effective_look(self):
        for (appearance, rule), expected in zip(self.input["looks"], self.js["looks"]):
            with self.subTest(appearance=appearance, look=rule):
                self.assertEqual(normal(look.effective_look(appearance, rule)), normal(expected))

    def test_pill_placement(self):
        for args, expected in zip(self.input["pills"], self.js["pills"]):
            w, h, scale, rule, pw, ph, pointer = args
            with self.subTest(args=args):
                self.assertEqual(look.pill_placement({"width": w, "height": h}, scale, rule, pw, ph, pointer), expected)

    def test_views(self):
        for view, expected in zip(self.input["views"], self.js["views"]):
            with self.subTest(title=view["state"]["title"], titles=view["state"]["titles"], details=view["details"]):
                self.assertEqual(normal(look.pill_content(view)), normal(expected["pill"]))
                self.assertEqual(normal(look.icon_layout(view)), normal(expected["icons"]))
                self.assertEqual(normal(look.pointer_placement(view)), normal(expected["pointer"]))
                self.assertEqual(look.is_selected_mode(view["state"]), expected["selected"])
                self.assertEqual(normal(look.segment_state(view["state"])), normal(expected["segments"]))

    def test_parse_color(self):
        for text, expected in zip(self.input["colors"], self.js["colors"]):
            with self.subTest(text=text):
                self.assertEqual(normal(look.parse_color(text, [9, 9, 9, 9])), normal(expected))

    def test_icon_names(self):
        for title, expected in zip(self.input["titles"], self.js["iconNames"]):
            self.assertEqual(look.icon_name_for(title), expected)


def js_constants(path):
    """const NAME = <number>; at the top level of a JavaScript file."""
    text = path.read_text()
    return {name: float(value) for name, value in re.findall(r"^(?:export )?const (\w+) = ([\d.]+);", text, re.M)}


class ConstantsTest(unittest.TestCase):
    def test_dial_geometry(self):
        constants = js_constants(DIAL_JS)
        for name in ("DIAL_D", "HINT_H", "ICON_R", "HIGHLIGHT_R", "GAUGE_R", "POINTER_GLOW_R", "ICON_SIZE",
                     "CENTER_ICON_SIZE"):
            self.assertEqual(getattr(look, name), constants[name], name)

    def test_painter_geometry(self):
        from overlay import painter

        constants = js_constants(DIAL_JS)
        for name in ("DIAL_D", "OUTER_R", "ICON_R", "BUBBLE_R", "HIGHLIGHT_R", "GAUGE_R", "GAUGE_W", "CENTER_R"):
            self.assertEqual(getattr(painter, name), constants[name], name)

    def test_extension_timing(self):
        constants = js_constants(EXTENSION_JS)
        for name in ("FADE_IN_MS", "FADE_OUT_MS", "FADE_AFTER_MS", "FADE_SLOW_MS", "PILL_ICON_SIZE"):
            self.assertEqual(getattr(look, name), constants[name], name)

    def test_positions_and_pointer_sides(self):
        from config import schema

        text = DIAL_JS.read_text()

        def js_list(name):
            return json.loads(re.search(rf"const {name} = (\[.*?\]);", text).group(1).replace("'", '"'))

        self.assertEqual(js_list("LOOK_POSITIONS"), list(look.LOOK_POSITIONS))
        self.assertEqual(list(schema.OVERLAY_POSITIONS), list(look.LOOK_POSITIONS))
        self.assertEqual(js_list("POINTER_SIDES"), list(look.POINTER_SIDES))
        self.assertEqual(list(schema.POINTER_SIDES), list(look.POINTER_SIDES))
        constants = js_constants(DIAL_JS)
        self.assertEqual((constants["POINTER_GAP"], constants["POINTER_GAP_MAX"]),
                         (look.POINTER_GAP, look.POINTER_GAP_MAX))
        self.assertEqual(schema.POINTER_GAP_MAX, look.POINTER_GAP_MAX)
        self.assertEqual((schema.OverlayConfig().pointer_side, schema.OverlayConfig().pointer_gap),
                         (look.POINTER_SIDES[0], look.POINTER_GAP))

    def test_extension_defaults(self):
        text = EXTENSION_JS.read_text()
        block = re.search(r"const DEFAULT_APPEARANCE = \{(.*?)\n\};", text, re.S).group(1)
        defaults = {}
        for key, value in re.findall(r"^\s*(\w+): (.+),$", block, re.M):
            defaults[key] = "glass" if value == "DEFAULT_SKIN" else json.loads(value.replace("'", '"'))
        self.assertEqual(defaults, look.DEFAULT_APPEARANCE)


class AppearanceTest(unittest.TestCase):
    def test_defaults(self):
        self.assertEqual(look.load_appearance(None), look.DEFAULT_APPEARANCE)

    def test_values_are_kept_in_range(self):
        appearance = look.load_appearance({"scale": 9, "hide_delay_ms": -5, "skin": "midnight", "accent": None})
        self.assertEqual(appearance["scale"], 1.6)
        self.assertEqual(appearance["hide_delay_ms"], 0)
        self.assertEqual(appearance["skin"], "midnight")
        self.assertEqual(appearance["accent"], "#e7b98d")
        # Number(x) || default, like the extension.
        self.assertEqual(look.load_appearance({"scale": "abc"})["scale"], 1)
        self.assertEqual(look.load_appearance({"scale": 0})["scale"], 1)
        self.assertEqual(look.load_appearance({"scale": "0.7"})["scale"], 0.7)
        self.assertEqual(look.load_appearance({"hide_delay_ms": 20000})["hide_delay_ms"], 10000)

    def test_light_skin_follows_the_desktop(self):
        appearance = look.load_appearance({"skin": "midnight", "skin_light": "frost", "follow_system_style": True})
        self.assertEqual(look.skin_id(appearance, prefers_dark=True), "midnight")
        self.assertEqual(look.skin_id(appearance, prefers_dark=False), "frost")
        appearance["follow_system_style"] = False
        self.assertEqual(look.skin_id(appearance, prefers_dark=False), "midnight")
        self.assertEqual(look.skin_id({"skin": ""}, prefers_dark=True), "glass")


class DriverStateTest(unittest.TestCase):
    def test_menu_titles_are_remembered(self):
        current = look.new_state()
        look.apply_overlay_state(current, (True, "Zoom", ["Zoom", "Volume"], ["", "x"], 0, 0.0, "", False, False, True))
        look.apply_overlay_state(current, (True, "Volume", ["", ""], ["", ""], 30, 0.0, "%", False, False, True))
        self.assertEqual(current["menuTitles"], ["Zoom", "Volume"])
        self.assertEqual(current["menuIcons"], ["", "x"])
        self.assertTrue(look.is_selected_mode(current))

    def test_legacy_driver_touches_while_enabled(self):
        current = look.new_state()
        look.apply_overlay_state(current, (True, "", [], [], 0, 0.0, "", False, False))
        self.assertTrue(current["touching"])

    def test_details_merge_and_ignore_garbage(self):
        details = look.new_details()
        look.merge_details(details, '{"profile": "Krita", "pointer": 90}')
        look.merge_details(details, "not json")
        look.merge_details(details, "[1, 2]")
        self.assertEqual(details["profile"], "Krita")
        self.assertEqual(details["pointer"], 90)
        self.assertEqual(details["mode"], "multi")

    def test_icon_source(self):
        self.assertEqual(look.icon_source("Volume", ""), "audio-volume-high-symbolic")
        self.assertEqual(look.icon_source("Volume", "my-icon"), "my-icon")
        self.assertEqual(look.icon_source("Volume", "/nonexistent/icon.svg"), "audio-volume-high-symbolic")
        self.assertEqual(look.icon_source("Volume", str(DIAL_JS)), str(DIAL_JS))


if __name__ == "__main__":
    unittest.main()
