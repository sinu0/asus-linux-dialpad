"""xkb.py against the system's libxkbcommon, and against python-xkbcommon
(the package it replaces) when that is installed."""

import gc
import os
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
# The failure tests would print libxkbcommon's compile errors.
os.environ.setdefault("XKB_LOG_LEVEL", "critical")

try:
    import xkb
except OSError as error:  # no libxkbcommon.so.0
    xkb = None
    MISSING = str(error)

try:
    from xkbcommon import xkb as reference
except ImportError:
    reference = None

# evdev keycode + 8
KEY_A = 38
KEY_Y = 29
KEY_Z = 52
KEY_LEFTSHIFT = 50
KEY_RIGHTALT = 108


KEYMAP_TEXT = """xkb_keymap {
    xkb_keycodes { include "evdev+aliases(qwerty)" };
    xkb_types { include "complete" };
    xkb_compat { include "complete" };
    xkb_symbols { include "pc+pl+inet(evdev)" };
};"""


def keysyms_of(keymap, xkb_module, layout):
    """Every (keycode, level, keysym names, modifier masks) of one layout."""
    result = []
    for keycode in keymap:
        if layout >= keymap.num_layouts_for_key(keycode):
            continue
        for level in range(keymap.num_levels_for_key(keycode, layout)):
            names = [xkb_module.keysym_get_name(sym) for sym in keymap.key_get_syms_by_level(keycode, layout, level)]
            result.append((keycode, level, names, keymap.key_get_mods_for_level(keycode, layout, level)))
    return result


@unittest.skipIf(xkb is None, "libxkbcommon is not installed")
class XkbTest(unittest.TestCase):
    def keymap(self, layout, variant=None):
        return xkb.Context(no_environment_names=True).keymap_new_from_names(layout=layout, variant=variant)

    def test_keysym_names_round_trip(self):
        for name in ("a", "Shift_L", "Control_L", "ISO_Level3_Shift", "BackSpace", "space", "aogonek"):
            with self.subTest(name=name):
                self.assertEqual(xkb.keysym_get_name(xkb.keysym_from_name(name)), name)
        self.assertEqual(xkb.keysym_from_name("no such keysym"), xkb.XKB_KEY_NoSymbol)
        self.assertEqual(xkb.keysym_from_name("BACKSPACE", case_insensitive=True), xkb.keysym_from_name("BackSpace"))

    def test_us_keymap(self):
        keymap = self.keymap("us")
        self.assertEqual(keymap.num_layouts(), 1)
        self.assertEqual(keymap.layout_get_name(0), "English (US)")
        self.assertIn(KEY_A, list(keymap))
        self.assertEqual([xkb.keysym_get_name(s) for s in keymap.key_get_syms_by_level(KEY_A, 0, 0)], ["a"])
        self.assertEqual([xkb.keysym_get_name(s) for s in keymap.key_get_syms_by_level(KEY_A, 0, 1)], ["A"])
        shift = 1 << [keymap.mod_get_name(i) for i in range(keymap.num_mods())].index("Shift")
        self.assertIn(shift, keymap.key_get_mods_for_level(KEY_A, 0, 1))
        self.assertEqual(keymap.key_get_syms_by_level(KEY_A, 0, 99), [])
        with self.assertRaises(xkb.XKBInvalidLayoutIndex):
            keymap.layout_get_name(5)
        with self.assertRaises(xkb.XKBInvalidModifierIndex):
            keymap.mod_get_name(1000)

    def test_two_layouts_and_a_variant(self):
        keymap = self.keymap("pl,de", ",nodeadkeys")
        self.assertEqual(keymap.num_layouts(), 2)
        self.assertEqual(keymap.layout_get_name(0), "Polish")
        self.assertEqual(keymap.num_layouts_for_key(KEY_Z), 2)
        # Polish has ą on AltGr+a; German swaps y and z.
        self.assertIn("aogonek", [xkb.keysym_get_name(s) for s in keymap.key_get_syms_by_level(KEY_A, 0, 2)])
        self.assertEqual([xkb.keysym_get_name(s) for s in keymap.key_get_syms_by_level(KEY_Z, 1, 0)], ["y"])
        self.assertEqual([xkb.keysym_get_name(s) for s in keymap.key_get_syms_by_level(KEY_Y, 1, 0)], ["z"])

    def test_state(self):
        keymap = self.keymap("pl")
        state = keymap.state_new()
        self.assertIs(state.get_keymap(), keymap)
        shift = [keymap.mod_get_name(i) for i in range(keymap.num_mods())].index("Shift")
        self.assertTrue(state.layout_index_is_active(0, xkb.StateComponent.XKB_STATE_LAYOUT_EFFECTIVE))
        self.assertFalse(state.mod_index_is_active(shift, xkb.StateComponent.XKB_STATE_MODS_DEPRESSED))
        changed = state.update_key(KEY_LEFTSHIFT, xkb.KeyDirection.XKB_KEY_DOWN)
        self.assertTrue(changed & xkb.StateComponent.XKB_STATE_MODS_DEPRESSED)
        self.assertTrue(state.mod_index_is_active(shift, xkb.StateComponent.XKB_STATE_MODS_DEPRESSED))
        self.assertFalse(state.update_key(KEY_A, xkb.KeyDirection.XKB_KEY_DOWN))
        state.update_key(KEY_LEFTSHIFT, xkb.KeyDirection.XKB_KEY_UP)
        self.assertFalse(state.mod_index_is_active(shift, xkb.StateComponent.XKB_STATE_MODS_DEPRESSED))
        with self.assertRaises(xkb.XKBInvalidLayoutIndex):
            state.layout_index_is_active(7, xkb.StateComponent.XKB_STATE_LAYOUT_EFFECTIVE)

    def test_keymap_from_buffer(self):
        # The Wayland compositor sends the keymap as a NUL-terminated string.
        data = KEYMAP_TEXT.encode() + b"\0"
        keymap = xkb.Context().keymap_new_from_buffer(data, length=len(data) - 1)
        self.assertEqual(keymap.layout_get_name(0), "Polish")
        with self.assertRaises(xkb.XKBKeymapCreationFailure):
            xkb.Context().keymap_new_from_buffer(b"not a keymap")

    def test_objects_outlive_their_creators(self):
        keymap = self.keymap("us")
        state = keymap.state_new()
        del keymap
        gc.collect()
        self.assertTrue(state.update_key(KEY_LEFTSHIFT, xkb.KeyDirection.XKB_KEY_DOWN))
        self.assertTrue(len(list(state.get_keymap())) > 0)

    def test_bad_names_raise(self):
        with self.assertRaises(xkb.XKBKeymapCreationFailure):
            self.keymap("no-such-layout")


@unittest.skipIf(xkb is None or reference is None, "python-xkbcommon is not installed")
class SameAsPythonXkbcommonTest(unittest.TestCase):
    def test_same_answers(self):
        for layout, variant in (("us", None), ("pl", None), ("de,us", "nodeadkeys,")):
            ours = xkb.Context(no_environment_names=True).keymap_new_from_names(layout=layout, variant=variant)
            theirs = reference.Context(no_environment_names=True).keymap_new_from_names(layout=layout, variant=variant)
            with self.subTest(layout=layout):
                self.assertEqual(list(ours), list(theirs))
                self.assertEqual(ours.num_mods(), theirs.num_mods())
                self.assertEqual([ours.mod_get_name(i) for i in range(ours.num_mods())],
                                 [theirs.mod_get_name(i) for i in range(theirs.num_mods())])
                for index in range(ours.num_layouts()):
                    self.assertEqual(ours.layout_get_name(index), theirs.layout_get_name(index))
                    self.assertEqual(keysyms_of(ours, xkb, index), keysyms_of(theirs, reference, index))

    def test_same_state_answers(self):
        ours = xkb.Context(no_environment_names=True).keymap_new_from_names(layout="pl")
        theirs = reference.Context(no_environment_names=True).keymap_new_from_names(layout="pl")
        for keycode in (KEY_LEFTSHIFT, KEY_RIGHTALT, KEY_A):
            a, b = ours.state_new(), theirs.state_new()
            changed = (a.update_key(keycode, xkb.KeyDirection.XKB_KEY_DOWN),
                       b.update_key(keycode, reference.KeyDirection.XKB_KEY_DOWN))
            with self.subTest(keycode=keycode):
                self.assertEqual(int(changed[0]), int(changed[1]))
                for mod in range(ours.num_mods()):
                    self.assertEqual(a.mod_index_is_active(mod, xkb.StateComponent.XKB_STATE_MODS_DEPRESSED),
                                     b.mod_index_is_active(mod, reference.StateComponent.XKB_STATE_MODS_DEPRESSED))

    def test_same_enums(self):
        for member in xkb.StateComponent:
            self.assertEqual(int(member), int(reference.StateComponent[member.name]))
        for member in xkb.KeyDirection:
            self.assertEqual(int(member), int(reference.KeyDirection[member.name]))


if __name__ == "__main__":
    unittest.main()
