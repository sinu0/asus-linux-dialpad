"""overlay/layer_shell.py starts safely: gtk4-layer-shell preloaded once,
a clear exit without layer-shell. The dial itself is tested on a compositor
by tests/layer_shell_in_container.sh (gtk4-layer-shell and sway are not
needed here)."""

import os
import subprocess
import sys
import unittest
from pathlib import Path

from overlay import layer_shell

ROOT = Path(__file__).resolve().parents[1]
ARGV = ["/usr/bin/python3", "overlay/layer_shell.py"]


class PreloadTest(unittest.TestCase):
    def test_restarts_with_the_library_preloaded(self):
        argv, environment = layer_shell.preload_command({"HOME": "/home/x"}, "libgtk4-layer-shell.so.0", ARGV)
        self.assertEqual(argv, ARGV)
        self.assertEqual(environment["LD_PRELOAD"], "libgtk4-layer-shell.so.0")
        self.assertEqual(environment[layer_shell.PRELOADED], "1")
        self.assertEqual(environment["HOME"], "/home/x")

    def test_keeps_other_preloaded_libraries(self):
        _argv, environment = layer_shell.preload_command({"LD_PRELOAD": "libfoo.so"}, "/usr/lib/libgtk4-layer-shell.so.0",
                                                         ARGV)
        self.assertEqual(environment["LD_PRELOAD"], "/usr/lib/libgtk4-layer-shell.so.0 libfoo.so")

    def test_restarts_at_most_once(self):
        self.assertIsNone(layer_shell.preload_command({layer_shell.PRELOADED: "1"}, "libgtk4-layer-shell.so.0", ARGV))
        self.assertIsNone(layer_shell.preload_command({"LD_PRELOAD": "/x/libgtk4-layer-shell.so.0"},
                                                      "libgtk4-layer-shell.so.0", ARGV))

    def test_without_the_library_it_does_not_restart(self):
        self.assertIsNone(layer_shell.preload_command({}, None, ARGV))


class StartTest(unittest.TestCase):
    def test_no_wayland_session_exits_with_status_3(self):
        environment = {key: value for key, value in os.environ.items() if key != "WAYLAND_DISPLAY"}
        run = subprocess.run([sys.executable, str(ROOT / "overlay" / "layer_shell.py")], env=environment,
                             capture_output=True, text=True, timeout=30)
        self.assertEqual(run.returncode, layer_shell.EXIT_UNSUPPORTED)
        self.assertIn("layer-shell", run.stderr)

    def test_runs_as_a_module_too(self):
        environment = {key: value for key, value in os.environ.items() if key != "WAYLAND_DISPLAY"}
        run = subprocess.run([sys.executable, "-m", "overlay.layer_shell", "--help"], cwd=ROOT, env=environment,
                             capture_output=True, text=True, timeout=30)
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertIn("--output", run.stdout)


if __name__ == "__main__":
    unittest.main()
