"""Every identifier in config/identity.py has twins outside Python; a rename
must change them together."""

import json
import re
import unittest
from pathlib import Path

from config import identity

ROOT = Path(__file__).resolve().parents[1]


def read(path):
    return (ROOT / path).read_text()


class IdentityTest(unittest.TestCase):
    def test_extension_uses_the_same_bus_and_config_dir(self):
        source = read("gnome/extension/extension.js")
        self.assertIn(f"const BUS_NAME = '{identity.DBUS_NAME}';", source)
        self.assertIn(f"const BUS_PATH = '{identity.DBUS_PATH}';", source)
        self.assertIn(f"GLib.get_user_config_dir(), '{identity.CONFIG_DIR_NAME}'", source)

    def test_extension_uuid(self):
        metadata = json.loads(read("gnome/extension/metadata.json"))
        self.assertEqual(metadata["uuid"], identity.GNOME_EXTENSION_UUID)
        self.assertIn(identity.GNOME_EXTENSION_UUID, read("install_gnome_extension.sh"))
        self.assertIn(identity.GNOME_EXTENSION_UUID, read("uninstall.sh"))

    def test_launcher(self):
        launcher = ROOT / "config_app" / f"{identity.APP_ID}.desktop"
        self.assertTrue(launcher.exists(), launcher)
        text = launcher.read_text()
        self.assertIn(f"Icon={identity.APP_ID}", text)
        self.assertIn(f"Name={identity.APP_NAME}", text)
        self.assertIn(f"{identity.APP_ID}.desktop", read("install.sh"))

    def test_install_dir_defaults(self):
        for script in ROOT.glob("install*.sh"):
            for default in re.findall(r'INSTALL_DIR_PATH="(/[^"]+)"', script.read_text()):
                with self.subTest(script=script.name):
                    self.assertEqual(default, identity.INSTALL_DIR)


if __name__ == "__main__":
    unittest.main()
