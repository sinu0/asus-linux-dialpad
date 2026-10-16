"""The installers copy the GNOME extension file by file; a new module that is
missing there only fails after the next login."""

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXTENSION = ROOT / "gnome" / "extension"


class InstallTest(unittest.TestCase):
    def test_installers_copy_every_extension_file(self):
        files = sorted(path.name for path in EXTENSION.iterdir() if path.suffix in {".js", ".json", ".css"})
        for script in ("install.sh", "install_gnome_extension.sh"):
            text = (ROOT / script).read_text()
            for name in files:
                with self.subTest(script=script, file=name):
                    self.assertIn(f"gnome/extension/{name}", text)


if __name__ == "__main__":
    unittest.main()
