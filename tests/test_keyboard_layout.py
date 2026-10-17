"""Keyboard layout names for the keymap the driver compiles without pywayland."""

import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from desktop import keyboard_layout


class KeyboardLayoutTest(unittest.TestCase):
    def test_gnome_sources(self):
        self.assertEqual(keyboard_layout.from_gnome("[('xkb', 'pl'), ('xkb', 'us')]", "@as []"),
                         {"layout": "pl,us"})
        self.assertEqual(
            keyboard_layout.from_gnome("[('xkb', 'de+nodeadkeys'), ('ibus', 'anthy'), ('xkb', 'us')]",
                                       "['ctrl:nocaps', 'compose:ralt']"),
            {"layout": "de,us,us", "variant": "nodeadkeys,,", "options": "ctrl:nocaps,compose:ralt"})

    def test_gnome_without_xkb_sources(self):
        self.assertIsNone(keyboard_layout.from_gnome("@a(ss) []"))
        self.assertIsNone(keyboard_layout.from_gnome("[('ibus', 'anthy')]"))
        self.assertIsNone(keyboard_layout.from_gnome("No such schema"))

    def test_gnome_keeps_at_most_four_layouts(self):
        sources = repr([("xkb", name) for name in ("us", "pl", "de", "fr", "cz")])
        self.assertEqual(keyboard_layout.from_gnome(sources), {"layout": "us,pl,de,fr"})

    def test_localectl(self):
        text = """System Locale: LANG=pl_PL.UTF-8
    VC Keymap: pl2
   X11 Layout: pl,us
    X11 Model: pc105
  X11 Variant: ,dvorak
  X11 Options: grp:alt_shift_toggle
"""
        self.assertEqual(keyboard_layout.from_localectl(text),
                         {"model": "pc105", "layout": "pl,us", "variant": ",dvorak", "options": "grp:alt_shift_toggle"})
        self.assertIsNone(keyboard_layout.from_localectl("System Locale: LANG=C.UTF-8\n    VC Keymap: (unset)\n"))
        self.assertIsNone(keyboard_layout.from_localectl(None))

    def test_environment(self):
        self.assertEqual(keyboard_layout.from_environment({"XKB_DEFAULT_LAYOUT": "fr", "XKB_DEFAULT_VARIANT": "bepo"}),
                         {"layout": "fr", "variant": "bepo"})
        self.assertIsNone(keyboard_layout.from_environment({"XKB_DEFAULT_VARIANT": "bepo"}))

    def test_order_and_fallback(self):
        outputs = {"gsettings": None, "localectl": None}

        def output(command):
            return outputs[command[0]]

        with mock.patch.object(keyboard_layout, "_output", output):
            self.assertEqual(keyboard_layout.rule_names({}), ({"layout": "us"}, "default"))
            self.assertEqual(keyboard_layout.rule_names({"XKB_DEFAULT_LAYOUT": "fr"})[0], {"layout": "fr"})
            outputs["localectl"] = "   X11 Layout: cz\n"
            self.assertEqual(keyboard_layout.rule_names({"XKB_DEFAULT_LAYOUT": "fr"}), ({"layout": "cz"}, "localectl"))
            outputs["gsettings"] = "[('xkb', 'pl')]"
            self.assertEqual(keyboard_layout.rule_names({})[0]["layout"], "pl")

    def test_names_compile(self):
        try:
            import xkb
        except OSError:
            self.skipTest("libxkbcommon is not installed")
        names = keyboard_layout.from_gnome("[('xkb', 'de+nodeadkeys'), ('ibus', 'anthy'), ('xkb', 'pl')]",
                                           "['ctrl:nocaps']")
        keymap = xkb.Context(no_environment_names=True).keymap_new_from_names(**names)
        self.assertEqual(keymap.num_layouts(), 3)
        self.assertEqual(keymap.layout_get_name(2), "Polish")


if __name__ == "__main__":
    unittest.main()
