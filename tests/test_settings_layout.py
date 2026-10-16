"""The settings app keeps its layout on monitors from 1080p to 4K.

tests/layout_probe.py opens the app (demo configuration, nothing saved) in a
headless mutter, so no window shows up, and reports widgets that reach past
the window at the sizes those monitors give it. Every size runs in its own
mutter at the same time.
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tests"))

TOOLS = ("mutter", "dbus-run-session")


def probe_sizes():
    # The probe imports GTK; read the sizes without starting it.
    namespace = {}
    source = (ROOT / "tests" / "layout_probe.py").read_text()
    start = source.index("SIZES = {")
    exec(source[start:source.index("}", start) + 1], namespace)
    return list(namespace["SIZES"])


@unittest.skipUnless(all(shutil.which(tool) for tool in TOOLS), "needs mutter for a headless display")
class SettingsLayoutTest(unittest.TestCase):
    def test_nothing_reaches_past_the_window(self):
        # GSettings defaults, not the desktop's fonts and settings.
        environment = {**os.environ, "GTK_A11Y": "none", "NO_AT_BRIDGE": "1", "GSETTINGS_BACKEND": "memory"}
        with tempfile.TemporaryDirectory(prefix="turnpad-layout-") as directory:
            runs = []
            for number, size in enumerate(probe_sizes()):
                output = Path(directory) / f"{number}.json"
                command = [
                    "dbus-run-session", "--", "mutter", "--headless", "--wayland", "--no-x11",
                    "--virtual-monitor", "3840x2160", "--wayland-display", f"turnpad-layout-{os.getpid()}-{number}",
                    "--", sys.executable, str(ROOT / "tests" / "layout_probe.py"), str(output), size,
                ]
                runs.append((size, output, subprocess.Popen(
                    command, env=environment, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True,
                )))
            faults = []
            for size, output, process in runs:
                _stdout, errors = process.communicate(timeout=120)
                if not output.exists():
                    self.fail(f"{size}: the probe did not finish\n{errors[-2000:]}")
                faults += json.loads(output.read_text())
                faults += [f"{size}: {line.strip()}" for line in errors.splitlines()
                           if "Gtk-CRITICAL" in line or "Gtk-WARNING" in line]
        self.assertEqual(faults, [], "\n".join(faults))


if __name__ == "__main__":
    unittest.main()
