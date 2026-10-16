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


def shell_value(name):
    """Value of NAME="..." or the default of : "${NAME:=...}" in install_paths.sh."""
    text = read("install_paths.sh")
    match = re.search(rf'^{name}="([^"]+)"', text, re.M) or re.search(rf'\$\{{{name}:=(.*)\}}"$', text, re.M)
    if match is None:
        raise AssertionError(f"{name} not found in install_paths.sh")
    return match.group(1).replace("$SLUG", identity.SLUG)


class IdentityTest(unittest.TestCase):
    def test_extension_uses_the_same_bus_and_config_dir(self):
        source = read("gnome/extension/extension.js")
        self.assertIn(f"const BUS_NAME = '{identity.DBUS_NAME}';", source)
        self.assertIn(f"const BUS_PATH = '{identity.DBUS_PATH}';", source)
        self.assertIn(f"GLib.get_user_config_dir(), '{identity.CONFIG_DIR_NAME}'", source)

    def test_extension_uuid(self):
        metadata = json.loads(read("gnome/extension/metadata.json"))
        self.assertEqual(metadata["uuid"], identity.GNOME_EXTENSION_UUID)

    def test_install_paths(self):
        self.assertEqual(shell_value("SLUG"), identity.SLUG)
        self.assertEqual(shell_value("APP_ID"), identity.APP_ID)
        self.assertEqual(shell_value("GNOME_EXTENSION_UUID"), identity.GNOME_EXTENSION_UUID)
        self.assertEqual(shell_value("INSTALL_DIR_PATH"), identity.INSTALL_DIR)
        self.assertTrue(shell_value("CONFIG_FILE_DIR_PATH").endswith(f"/{identity.CONFIG_DIR_NAME}"))

    def test_no_script_overrides_the_paths(self):
        # Defaults live in install_paths.sh only, so they cannot drift apart.
        for script in ROOT.glob("*install*.sh"):
            if script.name == "install_paths.sh":
                continue
            with self.subTest(script=script.name):
                self.assertNotRegex(script.read_text(), r'(?m)^\s*(INSTALL_DIR_PATH|CONFIG_FILE_DIR_PATH|LOGS_DIR_PATH)="/')

    def test_launcher(self):
        launcher = ROOT / "config_app" / f"{identity.APP_ID}.desktop"
        self.assertTrue(launcher.exists(), launcher)
        text = launcher.read_text()
        self.assertIn(f"Icon={identity.APP_ID}", text)
        self.assertIn(f"Name={identity.APP_NAME}", text)

    def test_service_templates_for_every_session(self):
        for kind in ("wayland", "x11", "plasma-wayland"):
            for name in (identity.SLUG, f"{identity.SLUG}-ui"):
                with self.subTest(service=f"{name}.{kind}.service"):
                    self.assertTrue((ROOT / f"{name}.{kind}.service").exists())


if __name__ == "__main__":
    unittest.main()
