"""The on-screen dial fits every common monitor, from 1080p to 4K.

GNOME places actors in logical pixels: a 4K panel at 200 % is 1920 × 1080,
the ProArt PX13 (2880 × 1800) at 200 % only 1440 × 900. overlayPlacement()
in dial.js runs in gjs for every monitor, dial size and position.
"""

import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# Physical size and GNOME scale factors people use with it.
MONITORS = {
    "1920x1080": (1920, 1080, (1, 1.25)),
    "1920x1200": (1920, 1200, (1, 1.25)),
    "2560x1440": (2560, 1440, (1, 1.25, 1.5)),
    "2560x1600": (2560, 1600, (1, 1.5, 2)),
    "2880x1800 (ProArt PX13)": (2880, 1800, (1.5, 1.75, 2)),
    "3440x1440": (3440, 1440, (1, 1.25)),
    "3840x2160 (4K)": (3840, 2160, (1, 1.5, 1.75, 2)),
}
POSITIONS = ("center", "lower", "bottom", "top")
DIAL_SCALES = (0.6, 1.0, 1.6)  # the settings app's range

SCRIPT = """
import { overlayPlacement } from '%s';
const cases = JSON.parse(ARGV[0]);
print(JSON.stringify(cases.map(([w, h, scale, position]) =>
    overlayPlacement({ width: w, height: h }, scale, position))));
"""


def logical(width, height, factor):
    return round(width / factor), round(height / factor)


@unittest.skipUnless(shutil.which("gjs"), "gjs is not installed")
class OverlayPlacementTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cases = []
        for name, (width, height, factors) in MONITORS.items():
            for factor in factors:
                w, h = logical(width, height, factor)
                for scale in DIAL_SCALES:
                    for position in POSITIONS:
                        cls.cases.append((f"{name} at {factor:g}x", w, h, scale, position))
        with tempfile.NamedTemporaryFile("w", suffix=".js") as script:
            script.write(SCRIPT % (ROOT / "gnome" / "extension" / "dial.js").as_uri())
            script.flush()
            result = subprocess.run(
                ["gjs", "-m", script.name, json.dumps([case[1:] for case in cls.cases])],
                capture_output=True, text=True, check=True,
            )
        cls.placements = json.loads(result.stdout.strip().splitlines()[-1])

    def each(self):
        for (name, w, h, scale, position), placed in zip(self.cases, self.placements):
            with self.subTest(monitor=name, scale=scale, position=position):
                yield w, h, scale, position, placed

    def test_dial_stays_on_the_monitor(self):
        for w, h, _scale, _position, placed in self.each():
            self.assertGreaterEqual(placed["x"], 0)
            self.assertGreaterEqual(placed["y"], 0)
            self.assertLessEqual(placed["x"] + placed["width"], w)
            self.assertLessEqual(placed["y"] + placed["height"], h)

    def test_dial_is_centred_and_sized_by_its_scale(self):
        for w, _h, scale, _position, placed in self.each():
            self.assertLessEqual(abs(placed["x"] * 2 + placed["width"] - w), 1)
            self.assertEqual(placed["width"], round(360 * scale))

    def test_positions_keep_their_order(self):
        by_screen = {}
        for w, h, scale, position, placed in self.each():
            by_screen.setdefault((w, h, scale), {})[position] = placed["y"]
        for (w, h, scale), y in by_screen.items():
            with self.subTest(monitor=f"{w}x{h}", scale=scale):
                self.assertLessEqual(y["top"], y["center"])
                self.assertLessEqual(y["center"], y["lower"])
                self.assertLessEqual(y["lower"], y["bottom"])


LOOK_SCRIPT = """
import { effectiveLook, overlayPlacement, pillContent, pillPlacement } from '%s';
const monitor = { width: 1440, height: 900 };
const appearance = { position: 'lower', custom_x: 0.5, custom_y: 0.5, visibility: 'full', fade_opacity: 35 };
const state = (title, titles = []) => ({
    title, titles, icons: titles.map(() => ''), menuTitles: ['Zoom', 'Volume'], menuIcons: ['', 'my-icon'],
    value: 64, unit: '%%', valueShowOnlyProgress: false,
});
const view = (title, titles) => ({ state: state(title, titles), details: { profile: 'Krita', colors: [] }, accent: [1, 0, 0, 1] });
const corners = [];
for (const x of [0, 0.5, 1])
    for (const y of [0, 0.5, 1])
        corners.push(overlayPlacement(monitor, 1.6, 'custom', [x, y]));
print(JSON.stringify({
    corners,
    middle: overlayPlacement({ width: 1920, height: 1080 }, 1, 'custom', [0.25, 0.75]),
    defaults: effectiveLook(appearance, {}),
    profile: effectiveLook(appearance, { position: 'custom', custom_x: 0.9, visibility: 'fade', fade_opacity: 50 }),
    invalid: effectiveLook(appearance, { position: 'side', custom_x: 7, visibility: 'loud', fade_opacity: -1 }),
    selected: pillContent(view('Volume', [])),
    hovered: pillContent(view('Zoom', ['Zoom', 'Volume'])),
    menu: pillContent(view('Menu', ['Zoom', 'Volume'])),
    pill: pillPlacement(monitor, 1, effectiveLook(appearance, { position: 'custom', custom_x: 1, custom_y: 0 }), 200, 40),
}));
"""


@unittest.skipUnless(shutil.which("gjs"), "gjs is not installed")
class DialLookTest(unittest.TestCase):
    """Custom position, profile and function overrides, and the pill."""

    @classmethod
    def setUpClass(cls):
        with tempfile.NamedTemporaryFile("w", suffix=".js") as script:
            script.write(LOOK_SCRIPT % (ROOT / "gnome" / "extension" / "dial.js").as_uri())
            script.flush()
            result = subprocess.run(["gjs", "-m", script.name], capture_output=True, text=True, check=True)
        cls.result = json.loads(result.stdout.strip().splitlines()[-1])

    def test_custom_position_stays_on_the_monitor(self):
        for placed in self.result["corners"]:
            self.assertGreaterEqual(placed["x"], 0)
            self.assertGreaterEqual(placed["y"], 0)
            self.assertLessEqual(placed["x"] + placed["width"], 1440)
            self.assertLessEqual(placed["y"] + placed["height"], 900)

    def test_custom_position_is_the_dial_centre(self):
        middle = self.result["middle"]
        self.assertEqual(middle["x"] + middle["width"] // 2, 480)
        self.assertEqual(middle["y"] + middle["width"] // 2, 810)

    def test_overrides_win_and_invalid_values_fall_back(self):
        self.assertEqual(self.result["defaults"],
                         {"position": "lower", "custom": [0.5, 0.5], "visibility": "full", "fadeOpacity": 0.35})
        self.assertEqual(self.result["profile"],
                         {"position": "custom", "custom": [0.9, 0.5], "visibility": "fade", "fadeOpacity": 0.5})
        self.assertEqual(self.result["invalid"], self.result["defaults"])

    def test_pill_shows_function_and_value(self):
        self.assertEqual(self.result["selected"]["title"], "Volume")
        self.assertEqual(self.result["selected"]["value"], "64%")
        self.assertEqual(self.result["selected"]["configured"], "my-icon")
        self.assertEqual((self.result["hovered"]["title"], self.result["hovered"]["value"]), ("Zoom", ""))
        self.assertEqual(self.result["menu"]["title"], "Krita")

    def test_pill_stays_on_the_monitor(self):
        self.assertEqual(self.result["pill"], {"x": 1240, "y": 0})


SUBMENU_SCRIPT = """
import GLib from 'gi://GLib';
import { overlayPlacement, openSubmenu, pillContent, submenuPlacement, submenuSize } from '%s';
// Too many cases for the command line: they come in a file.
const cases = JSON.parse(new TextDecoder().decode(GLib.file_get_contents(ARGV[0])[1]));
const placements = cases.map(([w, h, scale, position, custom, count, preferRight]) => {
    const monitor = { width: w, height: h };
    const dial = overlayPlacement(monitor, scale, position, custom);
    return { dial, list: submenuPlacement(monitor, dial, scale, submenuSize(count), preferRight) };
});
const menu = ['Zoom', 'Brush', 'Undo', 'Rotate', 'Mirror', 'System'];
const view = (index, selected, count) => ({
    state: { enabled: true, title: 'Item', titles: menu, icons: menu.map(() => ''), menuTitles: menu, menuIcons: [] },
    details: {
        profile: 'Krita', colors: [],
        submenu: { title: menu[index], items: Array.from({ length: count }, (_, n) => `Item ${n}`), selected },
    },
    accent: [1, 0, 0, 1],
});
const lists = [[1, 0, 3], [5, 0, 12], [5, 6, 12], [5, 11, 12], [5, 99, 12]].map(([index, selected, count]) => {
    const { first, rows, selected: chosen, preferRight } = openSubmenu(view(index, selected, count));
    return { first, rows, selected: chosen, preferRight };
});
const closed = openSubmenu({ ...view(1, 0, 3), details: { profile: '', colors: [], submenu: null } });
print(JSON.stringify({ placements, lists, closed, pill: pillContent(view(1, 1, 3)) }));
"""

# Inside the dial's box the disc leaves this much (logical pixels at scale
# 1) free at each side; the list's box has a margin for its shadow.
DIAL_MARGIN = 18
LIST_MARGIN = 12


@unittest.skipUnless(shutil.which("gjs"), "gjs is not installed")
class SubmenuPlacementTest(unittest.TestCase):
    """A group's list beside the dial fits every monitor and dial size."""

    @classmethod
    def setUpClass(cls):
        cls.cases = []
        for name, (width, height, factors) in MONITORS.items():
            for factor in factors:
                w, h = logical(width, height, factor)
                for scale in DIAL_SCALES:
                    for position in (*POSITIONS, "custom"):
                        customs = [[x, y] for x in (0, 0.5, 1) for y in (0, 1)] if position == "custom" else [None]
                        for custom in customs:
                            for count in (1, 7, 12):
                                for prefer_right in (True, False):
                                    cls.cases.append((f"{name} at {factor:g}x", w, h, scale, position, custom,
                                                      count, prefer_right))
        with tempfile.NamedTemporaryFile("w", suffix=".js") as script, \
                tempfile.NamedTemporaryFile("w", suffix=".json") as cases:
            script.write(SUBMENU_SCRIPT % (ROOT / "gnome" / "extension" / "dial.js").as_uri())
            script.flush()
            json.dump([case[1:] for case in cls.cases], cases)
            cases.flush()
            result = subprocess.run(["gjs", "-m", script.name, cases.name], capture_output=True, text=True, check=True)
        cls.result = json.loads(result.stdout.strip().splitlines()[-1])

    def each(self):
        for case, placed in zip(self.cases, self.result["placements"]):
            name, w, h, scale, position, custom, count, prefer_right = case
            with self.subTest(monitor=name, scale=scale, position=position, custom=custom, count=count,
                              right=prefer_right):
                yield w, h, scale, position, prefer_right, placed["dial"], placed["list"]

    def test_list_stays_on_the_monitor(self):
        for w, h, _scale, _position, _right, _dial, placed in self.each():
            self.assertGreaterEqual(placed["x"], 0)
            self.assertGreaterEqual(placed["y"], 0)
            self.assertLessEqual(placed["x"] + placed["width"], w)
            self.assertLessEqual(placed["y"] + placed["height"], h)

    def test_list_takes_the_preferred_side_and_leaves_the_disc_free(self):
        # The dial is centred horizontally, so both sides have the same room.
        for w, _h, scale, position, prefer_right, dial, placed in self.each():
            if position == "custom":
                continue
            self.assertEqual(placed["side"], "right" if prefer_right else "left")
            margin = DIAL_MARGIN * scale
            inset = LIST_MARGIN * placed["scale"]
            if placed["side"] == "right":
                self.assertGreaterEqual(placed["x"] + inset, dial["x"] + dial["width"] - margin - 1)
            else:
                self.assertLessEqual(placed["x"] + placed["width"] - inset, dial["x"] + margin + 1)

    def test_list_has_the_dial_scale_where_it_fits(self):
        for w, _h, scale, position, _right, dial, placed in self.each():
            self.assertLessEqual(placed["scale"], scale)
            self.assertGreaterEqual(placed["scale"], 0.6)
            # Common monitors at their usual scale have room for a normal dial.
            if position != "custom" and scale <= 1 and w >= 1280:
                self.assertEqual(placed["scale"], scale)

    def test_list_is_centred_on_the_dial(self):
        for _w, _h, _scale, position, _right, dial, placed in self.each():
            if position == "custom":
                continue
            self.assertLessEqual(abs(placed["y"] * 2 + placed["height"] - (dial["y"] * 2 + dial["width"])), 1)

    def test_list_near_an_edge_goes_to_the_side_with_room(self):
        for w, _h, _scale, position, _right, dial, placed in self.each():
            if position != "custom":
                continue
            if dial["x"] == 0:
                self.assertEqual(placed["side"], "right")
            elif dial["x"] + dial["width"] == w:
                self.assertEqual(placed["side"], "left")

    def test_visible_rows_follow_the_highlight(self):
        short, start, middle, end, past = self.result["lists"]
        self.assertEqual(short, {"first": 0, "rows": 3, "selected": 0, "preferRight": True})
        self.assertEqual((start["first"], start["rows"]), (0, 7))
        self.assertEqual((middle["first"], middle["selected"]), (3, 6))
        self.assertEqual((end["first"], end["selected"]), (5, 11))
        self.assertEqual(past["selected"], 11)
        # The last sector lies on the left half of the dial.
        self.assertFalse(start["preferRight"])
        self.assertIsNone(self.result["closed"])

    def test_pill_shows_the_highlighted_function(self):
        self.assertEqual(self.result["pill"]["title"], "Item")
        self.assertEqual(self.result["pill"]["value"], "2/3")


if __name__ == "__main__":
    unittest.main()
