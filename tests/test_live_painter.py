"""overlay/painter.py paints the live dial like the GNOME extension.

tests/render_dial_reference.js paints every case of tests/dial_cases.py
with dial.js in gjs; paint_live_dial() paints the same state in Python. Both
use the same icon files, so the pictures differ only by rendering noise
(the tolerance of tools/update_previews.py).
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

try:
    import cairo
    import gi

    gi.require_version("Rsvg", "2.0")
    from gi.repository import Rsvg
    import PIL  # noqa: F401
except (ImportError, ValueError):
    cairo = None

from dial_cases import CASES, MIN_PIXELS, case_view, changed_pixels, reference_cases  # noqa: E402
from overlay import look  # noqa: E402

ICON_THEMES = ["/usr/share/icons/Adwaita", "/usr/share/icons/AdwaitaLegacy", "/usr/share/icons/hicolor"]


def find_icon(name, cache={}):
    """findIcon() of render_dial_reference.js."""
    if name not in cache:
        cache[name] = None
        for theme in ICON_THEMES:
            found = _search(Path(theme), f"{name}.svg", 3) if Path(theme).is_dir() else None
            if found:
                cache[name] = found
                break
    return cache[name]


def _search(directory, file_name, depth):
    if (directory / file_name).exists():
        return str(directory / file_name)
    if depth == 0:
        return None
    for child in sorted(entry.name for entry in os.scandir(directory) if entry.is_dir()):
        found = _search(directory / child, file_name, depth - 1)
        if found:
            return found
    return None


def draw_icon(cr, name, x, y, size, color):
    path = name if name.startswith("/") else find_icon(name)
    if not path:
        return
    handle = Rsvg.Handle.new_from_file(path)
    cr.push_group()
    viewport = Rsvg.Rectangle()
    viewport.x, viewport.y, viewport.width, viewport.height = x, y, size, size
    handle.render_document(cr, viewport)
    mask = cr.pop_group()
    cr.set_source_rgba(*color)
    cr.mask(mask)


def paint_python(view, path, pixel_scale=1):
    from overlay.painter import paint_live_dial

    placement = look.overlay_placement({"width": 1920, "height": 1080}, view["appearance"]["scale"], "lower")
    surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, placement["width"] * pixel_scale,
                                 placement["height"] * pixel_scale)
    cr = cairo.Context(surface)
    cr.scale(pixel_scale, pixel_scale)
    paint_live_dial(cr, view, draw_icon)
    surface.write_to_png(str(path))


@unittest.skipUnless(shutil.which("gjs") and cairo is not None, "needs gjs, pycairo, Rsvg and Pillow")
class LivePainterTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.directory = tempfile.TemporaryDirectory(prefix="turnpad-live-painter-")
        cls.output = Path(cls.directory.name)
        cases = cls.output / "cases.json"
        cases.write_text(json.dumps(reference_cases()))
        subprocess.run(["gjs", "-m", str(ROOT / "tests" / "render_dial_reference.js"), str(cases),
                        str(cls.output / "reference")], check=True, capture_output=True, timeout=120)

    @classmethod
    def tearDownClass(cls):
        cls.directory.cleanup()

    def test_every_case_matches_dial_js(self):
        for case in CASES:
            with self.subTest(case=case["name"]):
                python = self.output / f"{case['name']}.png"
                paint_python(case_view(case), python)
                pixels = changed_pixels(self.output / "reference" / f"{case['name']}.png", python)
                self.assertIsNotNone(pixels, "sizes differ")
                self.assertLess(pixels, MIN_PIXELS)

    def test_layers_paint_like_the_whole_dial(self):
        # The layer-shell dial paints three layers; together they are the dial.
        from overlay.painter import paint_background, paint_content, paint_pointer

        view = case_view(CASES[1])
        scale = view["appearance"]["scale"]
        placement = look.overlay_placement({"width": 1920, "height": 1080}, scale, "lower")
        surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, placement["width"], placement["height"])
        cr = cairo.Context(surface)
        paint_background(cr, view)
        paint_content(cr, view, {}, draw_icon)
        pointer = look.pointer_placement(view)
        half = look.POINTER_SIZE * scale / 2
        cr.translate(pointer["x"] * scale - half, pointer["y"] * scale - half)
        paint_pointer(cr, view, pointer["color"])
        surface.write_to_png(str(self.output / "layers.png"))
        paint_python(view, self.output / "whole.png")
        self.assertLess(changed_pixels(self.output / "whole.png", self.output / "layers.png"), MIN_PIXELS)

    def test_twice_the_pixels(self):
        # HiDPI outputs: the cached centre disc follows the pixel density.
        from overlay.painter import paint_content

        view = case_view(CASES[0])
        surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, 720, 812)
        surface.set_device_scale(2, 2)
        cache = {}
        paint_content(cairo.Context(surface), view, cache)
        self.assertEqual(cache["center_image"].get_width(), 2 * 2 * 82)


if __name__ == "__main__":
    unittest.main()
