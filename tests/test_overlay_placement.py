"""The on-screen dial fits every common monitor, from 1080p to 4K.

GNOME places actors in logical pixels: a 4K panel at 200 % is 1920 × 1080,
the ProArt PX13 (2880 × 1800) at 200 % only 1440 × 900. overlayPlacement()
in dial.js runs in gjs for every monitor, dial size and position, and with
position "pointer" for pointers all over the monitor.
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
        pointer = {"pointerSide": "below-right", "pointerGap": 24}
        self.assertEqual(self.result["defaults"],
                         {"position": "lower", "custom": [0.5, 0.5], "visibility": "full", "fadeOpacity": 0.35,
                          **pointer})
        self.assertEqual(self.result["profile"],
                         {"position": "custom", "custom": [0.9, 0.5], "visibility": "fade", "fadeOpacity": 0.5,
                          **pointer})
        self.assertEqual(self.result["invalid"], self.result["defaults"])

    def test_pill_shows_function_and_value(self):
        self.assertEqual(self.result["selected"]["title"], "Volume")
        self.assertEqual(self.result["selected"]["value"], "64%")
        self.assertEqual(self.result["selected"]["configured"], "my-icon")
        self.assertEqual((self.result["hovered"]["title"], self.result["hovered"]["value"]), ("Zoom", ""))
        self.assertEqual(self.result["menu"]["title"], "Krita")

    def test_pill_stays_on_the_monitor(self):
        self.assertEqual(self.result["pill"], {"x": 1240, "y": 0})



SIDES = ("below-right", "below-left", "above-right", "above-left", "right", "left", "above", "below")
# Pointers as fractions of the monitor: corners, edges, centre.
SPOTS = ((0, 0), (1, 0), (0, 1), (1, 1), (0.5, 0.5), (0.5, 0), (0, 0.5), (1, 0.5), (0.5, 1), (0.2, 0.3), (0.85, 0.6))
GAPS = (0, 24, 120)

POINTER_SCRIPT = """
import { overlayPlacement, pillPlacement, effectiveLook } from '%s';
import GLib from 'gi://GLib';
const cases = JSON.parse(new TextDecoder().decode(GLib.file_get_contents(ARGV[0])[1]));
print(JSON.stringify(cases.map(([w, h, scale, pointer, side, gap]) => {
    const look = effectiveLook({ position: 'pointer', pointer_side: side, pointer_gap: gap }, {});
    return {
        dial: overlayPlacement({ width: w, height: h }, scale, 'pointer', null, pointer, side, gap),
        pill: pillPlacement({ width: w, height: h }, scale, look, 240, 44, pointer),
    };
})));
"""


@unittest.skipUnless(shutil.which("gjs"), "gjs is not installed")
class PointerPlacementTest(unittest.TestCase):
    """Position "pointer": next to the pointer, on screen, never over it."""

    @classmethod
    def setUpClass(cls):
        cls.cases = []
        for name, (width, height, factors) in MONITORS.items():
            for factor in factors:
                w, h = logical(width, height, factor)
                for scale in DIAL_SCALES:
                    for fx, fy in SPOTS:
                        # The last pixel is the farthest the pointer goes.
                        pointer = [min(w - 1, round(w * fx)), min(h - 1, round(h * fy))]
                        for side in SIDES:
                            for gap in GAPS:
                                cls.cases.append((f"{name} at {factor:g}x", w, h, scale, pointer, side, gap))
        with tempfile.NamedTemporaryFile("w", suffix=".js") as script, \
                tempfile.NamedTemporaryFile("w", suffix=".json") as data:
            script.write(POINTER_SCRIPT % (ROOT / "gnome" / "extension" / "dial.js").as_uri())
            script.flush()
            json.dump([case[1:] for case in cls.cases], data)
            data.flush()
            result = subprocess.run(["gjs", "-m", script.name, data.name], capture_output=True, text=True, check=True)
        cls.placements = json.loads(result.stdout.strip().splitlines()[-1])

    def each(self):
        for (name, w, h, scale, pointer, side, gap), placed in zip(self.cases, self.placements):
            with self.subTest(monitor=name, scale=scale, pointer=pointer, side=side, gap=gap):
                yield w, h, scale, pointer, side, gap, placed

    @staticmethod
    def away(pointer, x, y, width, height):
        """How far the pointer is outside the box (negative inside)."""
        px, py = pointer
        return max(x - px, px - x - width, y - py, py - y - height)

    def test_dial_and_pill_stay_on_the_monitor(self):
        for w, h, _scale, _pointer, _side, _gap, placed in self.each():
            dial, pill = placed["dial"], placed["pill"]
            self.assertGreaterEqual(min(dial["x"], dial["y"], pill["x"], pill["y"]), 0)
            self.assertLessEqual(dial["x"] + dial["width"], w)
            self.assertLessEqual(dial["y"] + dial["height"], h)
            self.assertLessEqual(pill["x"] + 240, w)
            self.assertLessEqual(pill["y"] + 44, h)

    @staticmethod
    def room(w, h, pointer, gap, width, height):
        """Whether a box fits on some side of the pointer, gap away."""
        px, py = pointer
        return px - gap - width >= 0 or px + gap + width <= w or py - gap - height >= 0 or py + gap + height <= h

    def test_pointer_stays_outside_the_dial(self):
        for w, h, _scale, pointer, _side, gap, placed in self.each():
            dial, pill = placed["dial"], placed["pill"]
            size = dial["width"], dial["height"]
            # With room for the gap the gap is kept; a large dial on a small
            # monitor may come closer, but never over the pointer.
            wanted = gap if self.room(w, h, pointer, gap, *size) else 0
            self.assertTrue(self.room(w, h, pointer, 0, *size))
            self.assertGreaterEqual(self.away(pointer, dial["x"], dial["y"], *size), wanted)
            self.assertGreaterEqual(self.away(pointer, pill["x"], pill["y"], 240, 44), gap)

    def test_gap_kept_with_the_default_gap(self):
        # 24 px fits on every monitor here, even at 200 % and the largest dial.
        for w, h, _scale, pointer, _side, gap, placed in self.each():
            dial = placed["dial"]
            if gap == 24:
                self.assertGreaterEqual(self.away(pointer, dial["x"], dial["y"], dial["width"], dial["height"]), 24)

    def test_chosen_side_wins_where_it_fits(self):
        # In the middle of the monitor every side fits for a small dial.
        for w, h, scale, pointer, side, gap, placed in self.each():
            if scale != 0.6 or gap != 24 or pointer != [round(w * 0.5), round(h * 0.5)]:
                continue
            dial = placed["dial"]
            px, py = pointer
            if "right" in side:
                self.assertEqual(dial["x"], px + gap)
            if "left" in side:
                self.assertEqual(dial["x"] + dial["width"], px - gap)
            if side.startswith("below"):
                self.assertEqual(dial["y"], py + gap)
            if side.startswith("above"):
                self.assertEqual(dial["y"] + dial["height"], py - gap)
            if side in ("right", "left"):
                self.assertEqual(dial["y"] + dial["width"] // 2, py)
            if side in ("above", "below"):
                self.assertEqual(dial["x"] + dial["width"] // 2, px)

    def test_side_flips_at_the_edge(self):
        for w, h, _scale, pointer, side, gap, placed in self.each():
            dial = placed["dial"]
            px, py = pointer
            if side == "below-right" and pointer == [w - 1, h - 1]:
                # Bottom right corner: above left of the pointer.
                self.assertEqual(dial["x"] + dial["width"], px - gap)
                self.assertEqual(dial["y"] + dial["height"], py - gap)
            if side == "right" and px == w - 1 and py == round(h * 0.5):
                self.assertEqual(dial["x"] + dial["width"], px - gap)


if __name__ == "__main__":
    unittest.main()
