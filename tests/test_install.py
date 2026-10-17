"""The installers copy files one by one; a module or extension file missing
there only fails on the next start or login."""

import ast
import re
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

    def test_package_copies_what_the_installer_copies(self):
        packaged = (ROOT / "packaging" / "install-files.sh").read_text()  # shared by all packages
        installer = (ROOT / "install.sh").read_text()
        for path in sorted(ROOT.glob("*.py")):
            if path.name == "dialpad_ui.py":
                # Legacy PySide overlay for desktops without the Shell extension.
                continue
            with self.subTest(module=path.name):
                self.assertIn(path.name, installer)
        # The packages take every module next to the driver but that one.
        self.assertIn("for module in *.py; do", packaged)
        self.assertIn("$module == dialpad_ui.py ]] || MODULES+=", packaged)
        for package in ("config", "config_app", "desktop", "layouts", "overlay"):
            with self.subTest(package=package):
                if package != "config_app":  # listed one by one, see below
                    self.assertIn(f"{package}/*.py", installer)
                self.assertRegex(packaged, rf"for dir in [^;]*\b{package}\b")
        for name in sorted(path.name for path in EXTENSION.iterdir() if path.suffix in {".js", ".json", ".css"}):
            with self.subTest(file=name):
                self.assertRegex(packaged, rf"gnome/extension/\{{[^}}]*\b{re.escape(name)}\b")
        for name in ("laptop_touchpad_dialpad_layouts.csv", "config_app/icon.svg", "config_app/style.css"):
            with self.subTest(file=name):
                self.assertIn(name, installer)
                self.assertIn(name, packaged)

    def test_every_package_installs_the_shared_file_list(self):
        # One list for the Arch, Debian and RPM packages, so a new file
        # cannot be missing from one of them.
        for recipe in ("arch/PKGBUILD", "deb/debian/rules", "rpm/asus-turnpad.spec"):
            text = (ROOT / "packaging" / recipe).read_text()
            with self.subTest(recipe=recipe):
                self.assertRegex(text, r"(?m)^\s*bash packaging/install-files\.sh ")
                self.assertNotRegex(text, r"(?m)^\s*install -")

    def test_rpm_lists_what_install_files_installs(self):
        # rpmbuild fails on installed but unlisted files only in a Fedora
        # container; every directory install-files.sh writes needs a line.
        spec = (ROOT / "packaging" / "rpm" / "asus-turnpad.spec").read_text()
        files = spec.split("\n%files\n", 1)[1]
        for path in ("%{_datadir}/%{name}\n", "%{_datadir}/gnome-shell/extensions/%{extension_uuid}\n",
                     "%{_datadir}/applications/", "%{_datadir}/icons/", "%{_userunitdir}/", "%{_udevrulesdir}/",
                     "%{_modulesloaddir}/", "%{_sysusersdir}/", "%{_bindir}/", "%{_docdir}/%{name}\n"):
            with self.subTest(path=path):
                self.assertIn(path, files)

    def test_debian_scripts_keep_the_debhelper_snippets(self):
        # dh_python3 adds py3compile/py3clean there; without them the
        # package has no bytecode.
        for script in ("postinst", "prerm", "postrm"):
            path = ROOT / "packaging" / "deb" / "debian" / script
            with self.subTest(script=script):
                self.assertIn("\n#DEBHELPER#\n", path.read_text())
                self.assertTrue(path.stat().st_mode & 0o111, "not executable")

    def test_installer_copies_every_settings_app_module(self):
        text = (ROOT / "install.sh").read_text()
        for path in sorted((ROOT / "config_app").glob("*.py")):
            with self.subTest(module=path.name):
                self.assertIn(f"config_app/{path.name}", text)


if __name__ == "__main__":
    unittest.main()
