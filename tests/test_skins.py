import json
import re
import tempfile
import unittest
from pathlib import Path

from config.schema import OverlayConfig, _decoder
from config.skins import (
    BUILTIN_SKINS_FILE,
    DIAL_SHAPES,
    DIR_KEY,
    FALLBACK_SKIN,
    OUTLINE_BOX,
    OUTLINE_RADIUS_MIN,
    PALETTE_KEYS,
    TILE_SHAPES,
    TILE_SIZE_MAX,
    color_to_hex,
    load_skins,
    mirror_index,
    new_skin_id,
    outline_limit,
    parse_color,
    resample_outline,
    resolve_skin,
    save_user_skin,
    without_private_keys,
)

DIAL_JS = Path(__file__).resolve().parents[1] / "gnome" / "extension" / "dial.js"


class BuiltinSkinsTest(unittest.TestCase):
    def setUp(self):
        with open(BUILTIN_SKINS_FILE) as handle:
            self.skins = json.load(handle)

    def test_every_builtin_skin_is_complete(self):
        keys = {key for key, _label, _help in PALETTE_KEYS}
        for skin_id, skin in self.skins.items():
            with self.subTest(skin=skin_id):
                self.assertEqual(set(skin["palette"]), keys)
                self.assertIn(skin["menu"], ("bubbles", "segments"))
                self.assertTrue(skin["name"])

    def test_fallback_matches_glass_and_dial_js(self):
        self.assertEqual(FALLBACK_SKIN["palette"], self.skins["glass"]["palette"])
        source = DIAL_JS.read_text()
        block = source[source.index("export const FALLBACK_SKIN"):source.index("};", source.index("export const FALLBACK_SKIN"))]
        js_keys = set(re.findall(r"^\s+(\w+): ", block, re.MULTILINE)) - {"name", "menu", "palette"}
        self.assertEqual(js_keys, set(FALLBACK_SKIN["palette"]) | {"shape", "tile", "tileSize"})


def js_list(name):
    source = DIAL_JS.read_text()
    match = re.search(rf"export const {name} = \[([^\]]*)\];", source)
    return tuple(re.findall(r"'([^']+)'", match.group(1)))


def js_number(name):
    return float(re.search(rf"export const {name} = ([\d.]+);", DIAL_JS.read_text()).group(1))


class ShapeTest(unittest.TestCase):
    def skins(self, **skin):
        skins = load_skins(Path(tempfile.mkdtemp()))
        skins["test"] = {"base": "glass", DIR_KEY: "/skins", **skin}
        return skins

    def test_shapes_and_limits_match_dial_js(self):
        self.assertEqual(js_list("DIAL_SHAPES"), DIAL_SHAPES)
        self.assertEqual(js_list("TILE_SHAPES"), TILE_SHAPES)
        self.assertEqual(js_number("OUTLINE_BOX"), OUTLINE_BOX)
        self.assertEqual(js_number("OUTLINE_RADIUS_MIN"), OUTLINE_RADIUS_MIN)
        self.assertEqual(js_number("TILE_SIZE_MAX"), TILE_SIZE_MAX)

    def test_shape_and_tiles_resolve_and_clamp(self):
        skin = resolve_skin(self.skins(shape="octagon", tile="hexagon", tileSize=9), "test")
        self.assertEqual((skin["shape"], skin["tile"], skin["tileSize"]), ("octagon", "hexagon", TILE_SIZE_MAX))
        skin = resolve_skin(self.skins(shape="blob", tile=3, tileSize="big"), "test")
        self.assertEqual((skin["shape"], skin["tile"], skin["tileSize"]), ("circle", "circle", 1))

    def test_custom_outline_stays_in_the_dial_square(self):
        skin = resolve_skin(self.skins(shape="custom", outline={"points": [2, 2, 0.1, 2], "smooth": False}), "test")
        self.assertEqual(skin["shape"], "custom")
        self.assertFalse(skin["outline"]["smooth"])
        self.assertEqual(skin["outline"]["points"], [OUTLINE_BOX, OUTLINE_BOX, OUTLINE_RADIUS_MIN, OUTLINE_BOX])
        # A full-size square reaches into the corners.
        self.assertAlmostEqual(outline_limit(1, 8), 1.5)
        # Without a usable outline the dial stays round.
        self.assertEqual(resolve_skin(self.skins(shape="custom", outline={"points": [1, 1]}), "test")["shape"], "circle")

    def test_background_picture_is_a_plain_png_next_to_the_skin(self):
        skin = resolve_skin(self.skins(background={"image": "photo.png", "opacity": 3}), "test")
        self.assertEqual(skin["background"], {"path": "/skins/photo.png", "opacity": 1.0})
        for image in ("../secret.png", "/etc/photo.png", "photo.jpg"):
            with self.subTest(image=image):
                self.assertIsNone(resolve_skin(self.skins(background={"image": image}), "test")["background"])

    def test_null_background_removes_the_base_picture(self):
        skins = self.skins(background=None)
        skins["glass"] = {**skins["glass"], "background": {"image": "a.png"}}
        self.assertIsNone(resolve_skin(skins, "test")["background"])

    def test_outline_helpers(self):
        self.assertEqual(resample_outline([1.0, 0.5], 4), [1.0, 0.75, 0.5, 0.75])
        self.assertEqual(len(resample_outline([1.0] * 6, 99)), 24)
        self.assertEqual([mirror_index(index, 8) for index in range(8)], [0, 7, 6, 5, 4, 3, 2, 1])

    def test_loader_notes_are_not_saved(self):
        self.assertEqual(without_private_keys({"name": "x", DIR_KEY: "/a"}), {"name": "x"})


class ResolveSkinTest(unittest.TestCase):
    def test_base_fills_missing_colours(self):
        skins = load_skins(Path("/nonexistent"))
        skins["mine"] = {"base": "frost", "menu": "segments", "palette": {"rim": "#ff000080"}}
        resolved = resolve_skin(skins, "mine")
        frost = resolve_skin(skins, "frost")
        self.assertEqual(resolved["menu"], "segments")
        self.assertEqual(resolved["palette"]["text"], frost["palette"]["text"])
        self.assertAlmostEqual(resolved["palette"]["rim"][3], 128 / 255)

    def test_broken_skin_still_paints(self):
        skins = {"bad": {"base": "bad", "menu": "spiral", "palette": {"text": "pink", "shadow": "lots"}}}
        resolved = resolve_skin(skins, "bad")
        self.assertEqual(resolved["menu"], "bubbles")
        self.assertEqual(resolved["palette"]["shadow"], FALLBACK_SKIN["palette"]["shadow"])
        self.assertEqual(len(resolved["palette"]["text"]), 4)

    def test_unknown_id_uses_default(self):
        skins = load_skins(Path("/nonexistent"))
        self.assertEqual(resolve_skin(skins, "missing"), resolve_skin(skins, "glass"))

    def test_colour_round_trip(self):
        self.assertEqual(color_to_hex(parse_color("#e7b98d", (0, 0, 0, 1))), "#e7b98d")
        self.assertEqual(color_to_hex(parse_color("#11223380", (0, 0, 0, 1))), "#11223380")
        self.assertEqual(parse_color([1, 0, 0], (0, 0, 0, 1)), (1.0, 0.0, 0.0, 1.0))


class UserSkinsTest(unittest.TestCase):
    def test_user_file_adds_a_skin(self):
        with tempfile.TemporaryDirectory() as directory:
            path = save_user_skin("night-owl", {"name": "Night owl", "base": "midnight"}, Path(directory))
            self.assertEqual(path.name, "night-owl.json")
            skins = load_skins(Path(directory))
            self.assertEqual(skins["night-owl"]["name"], "Night owl")
            self.assertIn("glass", skins)

    def test_new_id_avoids_clashes(self):
        self.assertEqual(new_skin_id("Dark glass!", {"dark-glass": {}}), "dark-glass-2")
        self.assertEqual(new_skin_id("", {}), "skin")

    def test_overlay_keeps_any_skin_name(self):
        self.assertEqual(_decoder({"skin": "night-owl"}, OverlayConfig).skin, "night-owl")
        self.assertEqual(_decoder({"skin": ""}, OverlayConfig).skin, "glass")
        self.assertEqual(_decoder({}, OverlayConfig).skin, "glass")

    def test_light_skin_defaults(self):
        overlay = _decoder({}, OverlayConfig)
        self.assertEqual(overlay.skin_light, "frost")
        self.assertFalse(overlay.follow_system_style)
        overlay = _decoder({"skin_light": None, "follow_system_style": 1}, OverlayConfig)
        self.assertEqual(overlay.skin_light, "frost")
        self.assertIs(overlay.follow_system_style, True)


if __name__ == "__main__":
    unittest.main()
