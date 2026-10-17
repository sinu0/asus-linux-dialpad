"""The driver's Wayland keymap lookup (keysym name → evdev keys) on xkb.py.

``dialpad.py`` opens devices at import time, so the lookup functions are
extracted from its syntax tree, as in test_driver_state.py, and run against
keymaps compiled from layout names (what the driver does without pywayland).
"""

import ast
import os
import sys
import unittest
from types import SimpleNamespace

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.environ.setdefault("XKB_LOG_LEVEL", "critical")

try:
    import xkb
except OSError:
    xkb = None

try:
    from xkbcommon import xkb as reference
except ImportError:
    reference = None

LOOKUP_FUNCTIONS = {"mod_name_to_specific_keysym_name", "load_evdev_key_for_wayland"}

KEY_1, KEY_Y, KEY_A, KEY_Z, KEY_LEFTSHIFT = 2, 21, 30, 44, 42
# <LVL3>, the first key with ISO_Level3_Shift (Right Alt comes later)
KEY_LEVEL3 = 84


def lookup(xkb_module, layout, layout_index=None):
    """load_evdev_key_for_wayland(name) for a keymap of these layouts."""
    with open(os.path.join(ROOT, "dialpad.py"), encoding="utf-8") as source:
        tree = ast.parse(source.read())
    functions = [node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name in LOOKUP_FUNCTIONS]
    keymap = xkb_module.Context(no_environment_names=True).keymap_new_from_names(layout=layout)
    namespace = {
        "xkb": xkb_module,
        "display": None,
        "X11_LIBS_AVAILABLE": False,
        "keyboard_state": keymap.state_new(),
        "gnome_current_layout_index": layout_index,
        # EV_KEY.codes[code] is the code itself here
        "EV_KEY": SimpleNamespace(codes=range(1024)),
        "enable_key": lambda key: None,
        "set_evdev_key_for_char": lambda char, key: None,
    }
    exec(compile(ast.Module(body=functions, type_ignores=[]), "dialpad.py", "exec"), namespace)
    return lambda name: namespace["load_evdev_key_for_wayland"](name, namespace["keyboard_state"])


@unittest.skipIf(xkb is None, "libxkbcommon is not installed")
class KeymapLookupTest(unittest.TestCase):
    def test_us(self):
        key = lookup(xkb, "us")
        self.assertEqual(key("a"), KEY_A)
        self.assertEqual(key("exclam"), [KEY_LEFTSHIFT, KEY_1])
        self.assertIsNone(key("aogonek"))

    def test_polish_altgr(self):
        key = lookup(xkb, "pl")
        self.assertEqual(key("aogonek"), [KEY_LEVEL3, KEY_A])

    def test_gnome_layout_index_picks_the_layout(self):
        self.assertEqual(lookup(xkb, "pl,de", layout_index=0)("y"), KEY_Y)
        self.assertEqual(lookup(xkb, "pl,de", layout_index=1)("y"), KEY_Z)

    @unittest.skipIf(reference is None, "python-xkbcommon is not installed")
    def test_same_keys_as_python_xkbcommon(self):
        names = ["a", "u", "space", "BackSpace", "Return", "exclam", "at", "Shift_L", "Control_L", "Alt_L",
                 "ISO_Level3_Shift", "Meta_L", "aogonek", "zabovedot", "y", "z", "EuroSign"]
        for layout in ("us", "pl", "de", "fr", "pl,us"):
            ours, theirs = lookup(xkb, layout), lookup(reference, layout)
            for name in names:
                with self.subTest(layout=layout, name=name):
                    self.assertEqual(ours(name), theirs(name))


if __name__ == "__main__":
    unittest.main()
