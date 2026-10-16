"""The installers copy files one by one; a module or extension file missing
there only fails on the next start or login."""

import ast
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

    def test_installer_copies_modules_the_driver_imports(self):
        tree = ast.parse((ROOT / "dialpad.py").read_text())
        names = {alias.name.split(".")[0] for node in ast.walk(tree) if isinstance(node, ast.Import) for alias in node.names}
        names |= {node.module.split(".")[0] for node in ast.walk(tree) if isinstance(node, ast.ImportFrom) and node.module}
        text = (ROOT / "install.sh").read_text()
        for name in sorted(names):
            if (ROOT / f"{name}.py").exists():
                with self.subTest(module=name):
                    self.assertRegex(text, rf"install .*\b{name}\.py")
            elif (ROOT / name / "__init__.py").exists():
                with self.subTest(package=name):
                    self.assertIn(f"{name}/*.py", text)


if __name__ == "__main__":
    unittest.main()
