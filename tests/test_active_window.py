import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

from desktop import active_window
from desktop.active_window import ActiveWindow, Backend, Context

try:
    from gi.repository import GLib
except ImportError:
    GLib = None

DBUS_DAEMON = shutil.which("dbus-daemon")

# A stand-in for GNOME Shell exporting the property the backend reads.
FAKE_SHELL = r"""
from gi.repository import Gio, GLib

info = Gio.DBusNodeInfo.new_for_xml('''<node><interface name="org.gnome.Shell">
  <property name="focusWindow" type="a{sv}" access="read"/>
</interface></node>''').interfaces[0]
bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)
bus.register_object(
    "/org/gnome/Shell", info, None,
    lambda *_args: GLib.Variant("a{sv}", {"title": GLib.Variant("s", "Doc - Krita")}), None,
)
bus.call_sync(
    "org.freedesktop.DBus", "/org/freedesktop/DBus", "org.freedesktop.DBus", "RequestName",
    GLib.Variant("(su)", ("org.gnome.Shell", 4)), None, Gio.DBusCallFlags.NONE, -1, None,
)
print("ready", flush=True)
GLib.MainLoop().run()
"""


class ActiveWindowTest(unittest.TestCase):
    def detector(self, session, *backends, display=None):
        return ActiveWindow(Context(session, x11_display=lambda: display, qdbus=None), list(backends))

    def test_first_answer_wins_in_order(self):
        calls = []

        def empty(_context):
            calls.append("empty")
            return None, None

        def found(_context):
            calls.append("found")
            return "/usr/bin/krita", "Krita"

        detector = self.detector("wayland", Backend("a", ("wayland",), empty), Backend("b", ("wayland",), found))
        self.assertEqual(detector.query(), ("/usr/bin/krita", "Krita"))
        self.assertEqual(calls, ["empty", "found"])

    def test_failing_backend_is_dropped_after_its_limit(self):
        calls = []

        def broken(_context):
            calls.append(1)
            raise FileNotFoundError("tool missing")

        detector = self.detector("wayland", Backend("broken", ("wayland",), broken, max_failures=2))
        for _ in range(5):
            self.assertEqual(detector.query(), (None, None))
        self.assertEqual(len(calls), 2)

    def test_x11_needs_an_open_display(self):
        x11 = Backend("x11", ("x11",), lambda _context: (None, "X window"), max_failures=None)
        wayland = Backend("w", ("wayland",), lambda _context: (None, "Wayland window"))
        self.assertEqual(self.detector("x11", x11, wayland, display=object()).query(), (None, "X window"))
        # Without a display the driver used to try the Wayland tools.
        self.assertEqual(self.detector("x11", x11, wayland).query(), (None, "Wayland window"))
        self.assertEqual(self.detector(None, x11, wayland).query(), (None, "Wayland window"))

    def test_registered_backends(self):
        from desktop.active_window import BACKENDS

        self.assertEqual([item.name for item in BACKENDS], ["x11", "kde", "gnome", "niri", "sway", "hyprland"])


@unittest.skipIf(GLib is None or DBUS_DAEMON is None, "needs PyGObject and dbus-daemon")
class GnomeBackendTest(unittest.TestCase):
    """The gnome backend against a fake Shell on a private session bus."""

    def setUp(self):
        self.home = tempfile.TemporaryDirectory()
        self.daemon = subprocess.Popen(
            [DBUS_DAEMON, "--session", "--nofork", "--print-address"],
            stdout=subprocess.PIPE, text=True,
        )
        self.address = self.daemon.stdout.readline().strip()
        self.assertTrue(self.address, "dbus-daemon printed no address")
        # Only for this test: the backend must never see the real session bus.
        environment = mock.patch.dict(os.environ, DBUS_SESSION_BUS_ADDRESS=self.address)
        environment.start()
        self.addCleanup(environment.stop)
        self.shell = None
        active_window._session_bus = None

    def tearDown(self):
        if active_window._session_bus is not None:
            active_window._session_bus.close_sync(None)
            active_window._session_bus = None
        if self.shell is not None:
            self.shell.terminate()
            self.shell.wait(5)
            self.shell.stdout.close()
        self.daemon.terminate()
        self.daemon.wait(5)
        self.daemon.stdout.close()
        self.home.cleanup()

    def start_shell(self):
        env = dict(os.environ, HOME=self.home.name, PYTHONWARNINGS="ignore::DeprecationWarning")
        self.shell = subprocess.Popen(
            [sys.executable, "-c", FAKE_SHELL], env=env, stdout=subprocess.PIPE, text=True,
        )
        self.assertEqual(self.shell.stdout.readline().strip(), "ready")

    def detector(self):
        return ActiveWindow(Context("wayland", qdbus=None), [Backend("gnome", ("wayland",), active_window.gnome)])

    def test_reads_the_focused_window_title(self):
        self.start_shell()
        self.assertEqual(active_window.gnome(Context("wayland", qdbus=None)), (None, "Doc - Krita"))
        self.assertEqual(self.detector().query(), (None, "Doc - Krita"))

    def test_without_shell_the_backend_fails_once(self):
        with self.assertRaises(GLib.Error):
            active_window.gnome(Context("wayland", qdbus=None))
        detector = self.detector()
        self.assertEqual(detector.query(), (None, None))
        self.assertEqual(detector.failures["gnome"], 1)


if __name__ == "__main__":
    unittest.main()
