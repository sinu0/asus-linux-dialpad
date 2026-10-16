"""Dial actions start programs without blocking the dial."""

import time
import unittest
from unittest import mock

import launch


class LaunchTest(unittest.TestCase):
    def setUp(self):
        # Plain processes: the systemd scope is not needed to test waiting.
        patcher = mock.patch.object(launch.shutil, "which", return_value=None)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_quick_commands_report_their_status(self):
        self.assertEqual(launch.run_shell("true"), 0)
        self.assertEqual(launch.run_shell("exit 3"), 3)

    def test_a_running_program_does_not_block(self):
        started = time.monotonic()
        self.assertIsNone(launch.run_shell("sleep 5", wait=0.2))
        self.assertLess(time.monotonic() - started, 2)

    def test_missing_program(self):
        self.assertEqual(launch.run(["/nonexistent/turnpad-test"]), 127)

    def test_systemd_scope_wraps_the_command(self):
        with mock.patch.object(launch.shutil, "which", return_value="/usr/bin/systemd-run"):
            self.assertEqual(
                launch.command_line(["gnome-calculator"]),
                ["/usr/bin/systemd-run", "--user", "--scope", "--quiet", "--collect", "--", "gnome-calculator"],
            )



class ImportedCommandsTest(unittest.TestCase):
    def test_commands_of_profiles_are_listed(self):
        from config.presets import calculator, volume
        from config.schema import MacroStep, Profile, StepType, shell_commands

        launcher = calculator()
        program = volume()
        program.macro_cw = [MacroStep(type=StepType.COMMAND, program="notify-send", args=["hi"])]
        profile = Profile(name="Shared", app_id=None, segments=[launcher, program])
        found = shell_commands([profile])
        self.assertIn(("Shared", "Calculator", launcher.macro_center[0].script), found)
        self.assertIn(("Shared", "Volume", "notify-send hi"), found)
        self.assertEqual(shell_commands([Profile(name="Plain", app_id=None, segments=[])]), [])


if __name__ == "__main__":
    unittest.main()
