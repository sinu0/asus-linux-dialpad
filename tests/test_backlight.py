"""Brightness levels of the DialPad light and their config section."""

import unittest

from backlight import LEVELS, commands_for_level, level_for_keyboard
from config.schema import BacklightConfig, DialPadConfig, _decoder, _encoder, _default_config


class BacklightTest(unittest.TestCase):
    def test_levels_map_to_touchpad_commands(self):
        self.assertEqual(commands_for_level(1), ["0x01", "0x41"])
        self.assertEqual(commands_for_level(LEVELS), ["0x01", "0x48"])
        self.assertEqual(commands_for_level(0), ["0x00"])
        # Out of range values are clamped, never sent as other commands.
        self.assertEqual(commands_for_level(12), ["0x01", "0x48"])
        self.assertEqual(commands_for_level(-3), ["0x00"])

    def test_keyboard_levels_spread_over_the_dialpad_levels(self):
        self.assertEqual([level_for_keyboard(value, 3) for value in range(4)], [0, 1, 5, 8])
        # Keyboard light off switches the DialPad light off too.
        self.assertEqual(level_for_keyboard(0, 3), 0)
        self.assertEqual(level_for_keyboard(1, 1), 8)
        self.assertEqual(level_for_keyboard(5, 0), LEVELS)

    def test_config_round_trip_and_clamping(self):
        config = _default_config()
        self.assertEqual(config.backlight, BacklightConfig())
        config.backlight = BacklightConfig(follow_keyboard=False, level=0)
        decoded = _decoder(_encoder(config), DialPadConfig)
        self.assertEqual(decoded.backlight, BacklightConfig(follow_keyboard=False, level=0))
        self.assertEqual(_decoder({"level": 42}, BacklightConfig).level, 8)
        # Configs written before the section existed keep the defaults.
        data = _encoder(_default_config())
        del data["backlight"]
        self.assertEqual(_decoder(data, DialPadConfig).backlight, BacklightConfig())


if __name__ == "__main__":
    unittest.main()
