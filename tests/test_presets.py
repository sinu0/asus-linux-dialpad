"""Function library and application packs: basic and advanced variants."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from config.presets import (  # noqa: E402
    APP_PACKS,
    BRIGHTNESS_QUERY,
    FUNCTION_LIBRARY,
    KBD_LIGHT_QUERY,
    LIBRARY_CATEGORIES,
    VOLUME_QUERY,
    pack_for_app,
    profile_for_app,
    profile_for_pack,
    variant_summary,
)
from config.profile_share import profile_json, profiles_from_text  # noqa: E402
from config.schema import (  # noqa: E402
    DialPadConfig,
    _decoder,
    _encoder,
    all_functions,
    overlay_rule,
    shell_commands,
)

try:
    import libevdev
except ImportError:  # the driver's library; not needed for the rest
    libevdev = None

VALUE_QUERIES = {VOLUME_QUERY, BRIGHTNESS_QUERY, KBD_LIGHT_QUERY}


def variants():
    for pack in APP_PACKS:
        for advanced in (False, True):
            yield pack, advanced, profile_for_pack(pack, advanced)


def functions(profile):
    return [segment for _group, segment in all_functions(profile.segments)]


class VariantsTest(unittest.TestCase):
    def test_every_pack_has_both_variants(self):
        for pack in APP_PACKS:
            with self.subTest(pack=pack.name):
                self.assertIsNotNone(pack.advanced)
                basic = pack.segments()
                advanced = pack.segments(True)
                self.assertLessEqual(len(basic), 6, "a basic menu stays short")
                self.assertTrue(all(not segment.is_group for segment in basic), "basic menus have no groups")
                self.assertLessEqual(len(advanced), 8, "sectors stay large enough to hit")
                count = len([item for _group, item in all_functions(advanced)])
                self.assertGreater(count, len(basic), "the advanced variant offers more")

    def test_groups_are_one_level_and_titles_unique(self):
        for pack, advanced, profile in variants():
            with self.subTest(pack=pack.name, advanced=advanced):
                titles = [segment.title for segment in profile.segments]
                self.assertEqual(len(titles), len(set(titles)))
                for segment in profile.segments:
                    if not segment.is_group:
                        continue
                    items = [item.title for item in segment.items]
                    self.assertGreaterEqual(len(items), 2, segment.title)
                    self.assertEqual(len(items), len(set(items)), segment.title)
                    self.assertNotIn(segment.title, items, "a group and its function share no name")
                    self.assertTrue(all(not item.is_group for item in segment.items))

    def test_every_function_does_something(self):
        for pack, advanced, profile in variants():
            for segment in functions(profile):
                with self.subTest(pack=pack.name, advanced=advanced, function=segment.title):
                    self.assertTrue(segment.macro_cw or segment.macro_center)
                    self.assertEqual(bool(segment.macro_cw), bool(segment.macro_ccw), "both turning directions")

    def test_dial_looks_are_valid(self):
        for pack, advanced, profile in variants():
            with self.subTest(pack=pack.name, advanced=advanced):
                self.assertEqual(overlay_rule(profile.overlay), profile.overlay)
                for segment in functions(profile):
                    self.assertEqual(overlay_rule(segment.overlay), segment.overlay, segment.title)
        looks = [segment.overlay for _pack, advanced, profile in variants() if advanced
                 for segment in functions(profile) if segment.overlay]
        self.assertTrue(looks, "advanced packs keep the dial out of the way somewhere")

    def test_only_value_queries_run_commands(self):
        for pack, advanced, profile in variants():
            with self.subTest(pack=pack.name, advanced=advanced):
                commands = {command for _profile, _title, command in shell_commands([profile])}
                self.assertLessEqual(commands, VALUE_QUERIES)

    @unittest.skipIf(libevdev is None, "python-libevdev is not installed")
    def test_keys_are_evdev_names(self):
        names = {code.name for code in libevdev.EV_KEY.codes}
        for pack, advanced, profile in variants():
            for segment in functions(profile):
                for steps in (segment.macro_cw, segment.macro_ccw, segment.macro_center):
                    for step in steps:
                        for key in (step.keys or []) + (step.modifiers or []):
                            with self.subTest(pack=pack.name, function=segment.title, key=key):
                                self.assertIn(key, names)

    def test_round_trips(self):
        for pack, advanced, profile in variants():
            with self.subTest(pack=pack.name, advanced=advanced):
                config = DialPadConfig(profiles=[profile])
                self.assertEqual(_encoder(_decoder(_encoder(config), DialPadConfig)), _encoder(config))
                (copy,) = profiles_from_text(profile_json(profile))
                self.assertEqual(_encoder(copy), _encoder(profile))

    def test_summaries(self):
        blender = pack_for_app("org.blender.Blender.desktop")
        self.assertEqual(variant_summary(blender), f"{len(blender.segments())} functions")
        self.assertIn("group", variant_summary(blender, True))

    def test_timeline_editors_show_their_menu_at_the_top(self):
        for app_id in ("org.kde.kdenlive.desktop", "com.blackmagicdesign.resolve.desktop"):
            pack = pack_for_app(app_id)
            self.assertEqual(profile_for_pack(pack, True).overlay, {"position": "top"})
            self.assertEqual(profile_for_pack(pack).overlay, {})


class PackMatchTest(unittest.TestCase):
    def test_desktop_ids(self):
        expected = {
            "org.gimp.GIMP.desktop": "GIMP",
            "org.kde.krita.desktop": "Krita",
            "org.blender.Blender.desktop": "Blender",
            "org.kde.kdenlive.desktop": "Kdenlive",
            "com.blackmagicdesign.resolve.desktop": "DaVinci Resolve",
            "org.darktable.darktable.desktop": "darktable",
            "org.audacityteam.Audacity.desktop": "Audacity",
            "com.obsproject.Studio.desktop": "OBS Studio",
            "firefox.desktop": "Browser",
            "org.mozilla.firefox.desktop": "Browser",
            "code.desktop": "Code editor",
            "codium.desktop": "Code editor",
            "org.gnome.Nautilus.desktop": "Files",
            "org.kde.dolphin.desktop": "Files",
            "vlc.desktop": "Video player",
            "io.mpv.Mpv.desktop": "Video player",
            "libreoffice-calc.desktop": "LibreOffice",
        }
        for app_id, name in expected.items():
            with self.subTest(app_id=app_id):
                self.assertEqual(pack_for_app(app_id).name, name)
        for app_id in ("org.gnome.Calculator.desktop", "org.gnome.Console.desktop", "org.gnome.Settings.desktop"):
            with self.subTest(app_id=app_id):
                self.assertIsNone(pack_for_app(app_id))

    def test_profile_for_app(self):
        basic = profile_for_app("Blender", "org.blender.Blender.desktop")
        advanced = profile_for_app("Blender", "org.blender.Blender.desktop", True)
        self.assertEqual(basic.name, "Blender")
        self.assertTrue(any(segment.is_group for segment in advanced.segments))
        self.assertFalse(profile_for_app("Calculator", "org.gnome.Calculator.desktop").segments)


class LibraryTest(unittest.TestCase):
    def test_presets_build_in_known_categories(self):
        titles = [preset.title for preset in FUNCTION_LIBRARY]
        self.assertEqual(len(titles), len(set(titles)))
        for preset in FUNCTION_LIBRARY:
            with self.subTest(preset=preset.title):
                segment = preset.factory()
                self.assertIn(preset.category, LIBRARY_CATEGORIES)
                self.assertEqual(segment.title, preset.title)
                self.assertEqual(segment.is_group, preset.category == "Groups")

    def test_ready_groups(self):
        groups = [preset.factory() for preset in FUNCTION_LIBRARY if preset.category == "Groups"]
        self.assertGreaterEqual(len(groups), 5)
        for group in groups:
            with self.subTest(group=group.title):
                titles = [item.title for item in group.items]
                self.assertGreaterEqual(len(titles), 3)
                self.assertEqual(len(titles), len(set(titles)))


if __name__ == "__main__":
    unittest.main()
