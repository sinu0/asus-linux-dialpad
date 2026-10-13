import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config.legacy_adapter import shortcuts_from_config  # noqa: E402
from config.schema import (  # noqa: E402
    DialPadConfig,
    MacroStep,
    Profile,
    Segment,
    StepType,
    _default_config,
)


def volume_segment():
    return Segment(
        title="Volume",
        macro_cw=[MacroStep(type=StepType.SHELL, script="true")],
        macro_ccw=[MacroStep(type=StepType.SHELL, script="true")],
        value_command="echo 42",
        unit="%",
        treshold=45,
    )


class LegacyAdapterTest(unittest.TestCase):
    def test_value_command_and_unit_reach_the_driver(self):
        config = DialPadConfig(profiles=[Profile(name="Default", segments=[volume_segment()])])
        segment = shortcuts_from_config(config)["none"]["Volume"]
        self.assertEqual(segment["value"], "echo 42")
        self.assertEqual(segment["unit"], "%")
        self.assertEqual(segment["treshold"], 45)

    def test_segment_without_value_has_no_value_key(self):
        config = DialPadConfig(profiles=[Profile(name="Default", segments=[Segment(title="Mute")])])
        segment = shortcuts_from_config(config)["none"]["Mute"]
        self.assertNotIn("value", segment)
        self.assertNotIn("unit", segment)

    def test_empty_app_profile_falls_back(self):
        config = DialPadConfig(profiles=[
            Profile(name="Firefox", app_id="firefox.desktop"),
            Profile(name="Default", segments=[volume_segment()]),
        ])
        shortcuts = shortcuts_from_config(config)
        self.assertNotIn("firefox.desktop", shortcuts)
        self.assertIn("Volume", shortcuts["none"])

    def test_default_config(self):
        shortcuts = shortcuts_from_config(_default_config())
        self.assertIn("none", shortcuts)

    def test_disabled_segments_are_hidden(self):
        config = DialPadConfig(profiles=[Profile(name="Default", segments=[
            volume_segment(), Segment(title="Off", enabled=False),
        ])])
        self.assertNotIn("Off", shortcuts_from_config(config)["none"])

    def test_profile_meta_and_hints(self):
        from config.legacy_adapter import META_KEY

        segment = volume_segment()
        segment.macro_cw[0].title = "Louder"
        segment.color = "#123456"
        config = DialPadConfig(profiles=[Profile(name="Default", sensitivity=2.0, segments=[segment])])
        profile = shortcuts_from_config(config)["none"]
        self.assertEqual(profile[META_KEY]["sensitivity"], 2.0)
        self.assertEqual(profile["Volume"]["hints"]["cw"], "Louder")
        self.assertEqual(profile["Volume"]["color"], "#123456")

    def test_single_mode_uses_flat_layout(self):
        from config.legacy_adapter import META_KEY

        config = DialPadConfig(profiles=[Profile(name="Default", mode="single", segments=[volume_segment()])])
        profile = shortcuts_from_config(config)["none"]
        self.assertNotIn("Volume", profile)
        self.assertTrue(profile["clockwise"])
        self.assertEqual(profile[META_KEY]["single"]["treshold"], 45)
        self.assertEqual(profile[META_KEY]["single"]["value"], "echo 42")


class SchemaRoundTripTest(unittest.TestCase):
    def test_new_fields_survive_save_and_load(self):
        from config.schema import OverlayConfig, _decoder, _encoder

        step = MacroStep(type=StepType.SCROLL, direction="clockwise", value=60,
                         axis="horizontal", modifiers=["KEY_LEFTCTRL"])
        config = DialPadConfig(
            overlay=OverlayConfig(scale=1.2, position="bottom"),
            profiles=[Profile(name="P", mode="single", single_function="S", scroll_speed=1.5,
                              remember_last=False,
                              segments=[Segment(title="S", color="#abcdef", enabled=False, macro_cw=[step])])],
        )
        loaded = _decoder(_encoder(config), DialPadConfig)
        self.assertEqual(loaded, config)

    def test_old_files_get_defaults_and_bad_values_are_clamped(self):
        from config.schema import _decoder

        loaded = _decoder({
            "geometry": {"width": 1, "height": 1, "circle_diameter": 1, "center_button_diameter": 1,
                         "center_x": 1, "center_y": 1},
            "overlay": {"scale": 9, "position": "nowhere"},
            "profiles": [{"name": "Old", "mode": "weird", "sensitivity": "x",
                          "segments": [{"title": "T", "unknown": 1}]}],
        }, DialPadConfig)
        self.assertEqual(loaded.overlay.scale, 1.6)
        self.assertEqual(loaded.overlay.position, "lower")
        self.assertEqual(loaded.profiles[0].mode, "multi")
        self.assertEqual(loaded.profiles[0].sensitivity, 1.0)
        self.assertTrue(loaded.profiles[0].segments[0].enabled)


class PresetsTest(unittest.TestCase):
    def test_library_presets_are_valid_and_labelled(self):
        from config.labels import describe_macro
        from config.presets import APP_PACKS, FUNCTION_LIBRARY

        segments = [preset.factory() for preset in FUNCTION_LIBRARY]
        for pack in APP_PACKS:
            segments.extend(pack.factory())
        for segment in segments:
            self.assertTrue(segment.macro_cw or segment.macro_center, segment.title)
            for step in segment.macro_cw + segment.macro_ccw:
                self.assertTrue(describe_macro([step]), segment.title)

    def test_packs_match_desktop_ids(self):
        from config.presets import pack_for_app, profile_for_app

        self.assertEqual(pack_for_app("org.kde.krita.desktop").name, "Krita")
        self.assertEqual(pack_for_app("firefox.desktop").name, "Browser")
        self.assertIsNone(pack_for_app("org.gnome.Calculator.desktop"))
        self.assertTrue(profile_for_app("darktable", "org.darktable.darktable.desktop").segments)
        self.assertEqual(pack_for_app("com.obsproject.Studio.desktop").name, "OBS Studio")

    def test_pack_titles_are_unique(self):
        from config.presets import APP_PACKS

        for pack in APP_PACKS:
            titles = [segment.title for segment in pack.factory()]
            self.assertEqual(len(titles), len(set(titles)), pack.name)


if __name__ == "__main__":
    unittest.main()
