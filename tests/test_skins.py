import json
import re
import tempfile
import unittest
from pathlib import Path

from config.schema import OverlayConfig, _decoder
from config.skins import (
    BUILTIN_SKINS_FILE,
    FALLBACK_SKIN,
    PALETTE_KEYS,
    color_to_hex,
    load_skins,
    new_skin_id,
    parse_color,
    resolve_skin,
    save_user_skin,
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
        self.assertEqual(js_keys, set(FALLBACK_SKIN["palette"]))


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
