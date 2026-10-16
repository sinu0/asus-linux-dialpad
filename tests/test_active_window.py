import unittest

from desktop.active_window import ActiveWindow, Backend, Context


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


if __name__ == "__main__":
    unittest.main()
