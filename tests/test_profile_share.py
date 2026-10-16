import json
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config.presets import profile_for_pack, pack_for_app  # noqa: E402
from config.profile_share import ProfileTextError, ai_prompt, profile_json, profiles_from_text  # noqa: E402
from config.schema import Profile, StepType, _encoder, shell_commands  # noqa: E402

# An assistant's answer to ai_prompt() for "Files (Nautilus): zoom, back/forward
# history, tabs, show hidden files and a terminal launcher", with the prose,
# code fence and short key names assistants tend to add.
ASSISTANT_ANSWER = """Here is a profile for GNOME Files:

```json
{
  "name": "Files",
  "app_id": "org.gnome.Nautilus.desktop",
  "mode": "multi",
  "sensitivity": 1.0,
  "scroll_speed": 1.0,
  "remember_last": true,
  "segments": [
    {
      "title": "Zoom",
      "color": "#e7b98d",
      "treshold": 30,
      "macro_cw": [{"type": "keystroke", "keys": ["KEY_LEFTCTRL", "KEY_EQUAL"], "title": "Larger icons"}],
      "macro_ccw": [{"type": "keystroke", "keys": ["KEY_LEFTCTRL", "KEY_MINUS"], "title": "Smaller icons"}],
      "macro_center": [{"type": "keystroke", "keys": ["Ctrl", "0"], "title": "Normal size"}]
    },
    {
      "title": "History",
      "icon_url": "go-previous-symbolic",
      "macro_cw": [{"type": "keystroke", "keys": ["KEY_LEFTALT", "KEY_RIGHT"], "title": "Forward"}],
      "macro_ccw": [{"type": "keystroke", "keys": ["KEY_LEFTALT", "KEY_LEFT"], "title": "Back"}],
      "macro_center": [{"type": "keystroke", "keys": ["KEY_LEFTALT", "KEY_UP"], "title": "Parent folder"}]
    },
    {
      "title": "Tabs",
      "macro_cw": [{"type": "keystroke", "keys": ["KEY_LEFTCTRL", "KEY_PAGEDOWN"], "title": "Next tab"}],
      "macro_ccw": [{"type": "keystroke", "keys": ["KEY_LEFTCTRL", "KEY_PAGEUP"], "title": "Previous tab"}],
      "macro_center": [{"type": "keystroke", "keys": ["KEY_LEFTCTRL", "KEY_T"], "title": "New tab"}]
    },
    {
      "title": "Scroll",
      "macro_cw": [{"type": "scroll", "direction": "clockwise", "value": 120}],
      "macro_ccw": [{"type": "scroll", "direction": "counterclockwise", "value": 120}]
    },
    {
      "title": "Hidden files",
      "icon_url": "view-reveal-symbolic",
      "macro_cw": [],
      "macro_ccw": [],
      "macro_center": [{"type": "keystroke", "keys": ["KEY_LEFTCTRL", "KEY_H"], "title": "Show hidden files"}]
    },
    {
      "title": "Terminal",
      "color": "not a colour",
      "macro_cw": [],
      "macro_ccw": [],
      "macro_center": [{"type": "shell", "script": "kgx || gnome-terminal", "title": "Open a terminal"}]
    }
  ]
}
```

Turn Zoom to resize icons; tap the centre to reset."""


class ProfileShareTest(unittest.TestCase):
    def test_prompt_holds_the_format_and_the_profile(self):
        profile = Profile(name="Files", app_id="org.gnome.Nautilus.desktop")
        prompt = ai_prompt(profile)
        self.assertIn('"keystroke"', prompt)
        self.assertTrue(prompt.endswith("My idea: "))
        self.assertEqual(profiles_from_text(prompt)[0].app_id, profile.app_id)

    def test_round_trip_of_a_preset(self):
        profile = profile_for_pack(pack_for_app("org.gimp.GIMP.desktop"))
        (copy,) = profiles_from_text(profile_json(profile))
        self.assertEqual(_encoder(copy), _encoder(profile))

    def test_reads_an_assistant_answer(self):
        (profile,) = profiles_from_text(ASSISTANT_ANSWER)
        self.assertEqual(profile.app_id, "org.gnome.Nautilus.desktop")
        self.assertEqual([segment.title for segment in profile.segments],
                         ["Zoom", "History", "Tabs", "Scroll", "Hidden files", "Terminal"])
        zoom = profile.segments[0]
        self.assertEqual(zoom.treshold, 30)
        # Short key names become the evdev names the driver sends.
        self.assertEqual(zoom.macro_center[0].keys, ["KEY_LEFTCTRL", "KEY_0"])
        self.assertIsNone(profile.segments[5].color)
        self.assertEqual(profile.segments[3].macro_cw[0].type, StepType.SCROLL)
        # The import dialog lists the command before anything runs.
        self.assertEqual(shell_commands([profile]), [("Files", "Terminal", "kgx || gnome-terminal")])

    def test_reads_an_export_file(self):
        profiles = [Profile(name="A"), Profile(name="B", app_id="b.desktop")]
        text = json.dumps({"dialpad_profiles": 1, "profiles": [_encoder(item) for item in profiles]})
        self.assertEqual([profile.name for profile in profiles_from_text(text)], ["A", "B"])

    def test_explains_what_is_wrong(self):
        cases = {
            "no json here": "No JSON found",
            '{"name": "X"}': "no \"segments\"",
            '{"segments": [{"macro_cw": []}]}': "has no \"title\"",
            '{"segments": [{"title": "T", "macro_cw": [{"type": "press"}]}]}': "unknown step type",
            '{"segments": [{"title": "T", "macro_cw": [{"type": "keystroke", "keys": ["Hyper", "Q"]}]}]}':
                "unknown key Hyper",
            '{"segments": [{"title": "T", "macro_cw": [{"type": "shell"}]}]}': "needs a \"script\"",
        }
        for text, message in cases.items():
            with self.subTest(text=text):
                with self.assertRaises(ProfileTextError) as caught:
                    profiles_from_text(text)
                self.assertIn(message, str(caught.exception))

    def test_titles_stay_unique_and_single_mode_has_a_function(self):
        text = json.dumps({"name": "P", "mode": "single", "single_function": "Missing",
                           "segments": [{"title": "Zoom"}, {"title": "zoom"}]})
        (profile,) = profiles_from_text(text)
        self.assertEqual([segment.title for segment in profile.segments], ["Zoom", "zoom 2"])
        self.assertEqual(profile.single_function, "Zoom")


if __name__ == "__main__":
    unittest.main()
