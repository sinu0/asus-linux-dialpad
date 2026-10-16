import os
import re
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config.labels import ICON_RULES, keys_to_text, order_keys, parse_keys  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class ParseKeysTest(unittest.TestCase):
    def test_reads_typed_shortcuts(self):
        self.assertEqual(parse_keys("F12"), (["KEY_F12"], []))
        self.assertEqual(parse_keys("Ctrl+F12"), (["KEY_LEFTCTRL", "KEY_F12"], []))
        self.assertEqual(parse_keys("ctrl shift z"), (["KEY_LEFTCTRL", "KEY_LEFTSHIFT", "KEY_Z"], []))
        self.assertEqual(parse_keys("Ctrl + ["), (["KEY_LEFTCTRL", "KEY_LEFTBRACE"], []))
        self.assertEqual(parse_keys("KEY_LEFTALT KEY_LEFT"), (["KEY_LEFTALT", "KEY_LEFT"], []))

    def test_puts_modifiers_first(self):
        self.assertEqual(parse_keys("F12+Ctrl")[0], ["KEY_LEFTCTRL", "KEY_F12"])
        self.assertEqual(order_keys(["KEY_Z", "KEY_LEFTSHIFT", "KEY_Z"]), ["KEY_LEFTSHIFT", "KEY_Z"])

    def test_reports_unknown_words(self):
        self.assertEqual(parse_keys("Hyper+Q"), (["KEY_Q"], ["Hyper"]))
        self.assertEqual(parse_keys("F99")[1], ["F99"])

    def test_text_reads_back(self):
        keys = ["KEY_LEFTCTRL", "KEY_LEFTMETA", "KEY_PAGEUP", "KEY_LEFTBRACE", "KEY_BACKSLASH",
                "KEY_LEFT", "KEY_EQUAL", "KEY_HOME", "KEY_SYSRQ", "KEY_F12"]
        self.assertEqual(parse_keys(keys_to_text(keys)), (keys, []))
        self.assertEqual(keys_to_text(["KEY_LEFTCTRL", "KEY_F12"]), "Ctrl+F12")
        # Old configurations store raw evdev codes.
        self.assertEqual(keys_to_text(["29", "KEY_Z"]), "Ctrl+Z")


class IconRulesTest(unittest.TestCase):
    def test_overlay_uses_the_same_rules(self):
        with open(os.path.join(ROOT, "gnome", "extension", "dial.js")) as handle:
            source = handle.read()
        block = source[source.index("const ICON_RULES = ["):source.index("];", source.index("const ICON_RULES"))]
        rules = tuple(
            (tuple(re.findall(r"'([^']+)'", words)), icon)
            for words, icon in re.findall(r"\[\[([^\]]*)\], '([^']+)'\]", block)
        )
        self.assertEqual(rules, ICON_RULES)


if __name__ == "__main__":
    unittest.main()
