"""overlay/visibility.py shows, fades and hides the dial like extension.js."""

import unittest

from overlay import look
from overlay.visibility import Visibility


class FakeActor:
    def __init__(self, name):
        self.name = name
        self.visible = False
        self.opacity = 0
        self.eases = []
        self._done = None

    def ease(self, opacity, duration, easing, on_complete=None):
        self.eases.append((opacity, duration, easing))
        # Ends at once; on_complete runs when the test finishes it.
        self.opacity = opacity
        self._done = on_complete

    def finish(self):
        done, self._done = self._done, None
        if done:
            done()

    def remove_all_transitions(self):
        self._done = None


class FakeTimers:
    def __init__(self):
        self.now = 0
        self.pending = {}
        self._next = 0

    def add(self, milliseconds, callback):
        self._next += 1
        self.pending[self._next] = (self.now + milliseconds, callback)
        return self._next

    def remove(self, handle):
        del self.pending[handle]

    def advance(self, milliseconds):
        end = self.now + milliseconds
        while True:
            due = [(when, handle) for handle, (when, _cb) in self.pending.items() if when <= end]
            if not due:
                break
            when, handle = min(due)
            self.now = when
            _when, callback = self.pending.pop(handle)
            callback()
        self.now = end


class VisibilityTest(unittest.TestCase):
    def setUp(self):
        self.dial, self.pill = FakeActor("dial"), FakeActor("pill")
        self.timers = FakeTimers()
        self.state = look.new_state()
        self.look = {"visibility": "full", "fadeOpacity": 0.35, "position": "lower", "custom": [0.5, 0.5]}
        self.visibility = Visibility(self.dial, self.pill, self.timers, lambda: self.look, lambda: self.state,
                                     lambda: 1500)

    def signal(self, enabled, touching):
        was_enabled, was_touching = self.state["enabled"], self.state["touching"]
        self.state["enabled"], self.state["touching"] = enabled, touching
        self.visibility.update(was_enabled, was_touching)

    def test_shows_while_touching_and_lingers_after_release(self):
        self.signal(True, True)
        self.assertTrue(self.dial.visible)
        self.assertEqual(self.dial.eases[-1], (255, look.FADE_IN_MS, look.ease_out_quad))
        self.timers.advance(5000)
        self.assertTrue(self.dial.visible, "never hides while touching")
        self.signal(True, False)
        self.timers.advance(1499)
        self.assertEqual(self.dial.opacity, 255)
        self.timers.advance(1)
        self.assertEqual(self.dial.eases[-1], (0, look.FADE_OUT_MS, look.ease_in_quad))
        self.dial.finish()
        self.assertFalse(self.dial.visible)

    def test_new_touch_keeps_a_lingering_dial(self):
        self.signal(True, True)
        self.signal(True, False)
        self.timers.advance(1000)
        self.signal(True, True)
        self.timers.advance(5000)
        self.assertEqual(self.dial.opacity, 255)
        self.assertTrue(self.dial.visible)

    def test_signals_while_touching_do_not_restart_the_fade_in(self):
        self.signal(True, True)
        eases = len(self.dial.eases)
        for _ in range(5):
            self.signal(True, True)
        self.assertEqual(len(self.dial.eases), eases)

    def test_activation_flashes_the_dial(self):
        self.signal(True, False)
        self.assertTrue(self.dial.visible)
        self.timers.advance(1500)
        self.dial.finish()
        self.assertFalse(self.dial.visible)

    def test_a_hidden_dial_stays_hidden_without_touch(self):
        self.signal(True, False)
        self.timers.advance(1500)
        self.dial.finish()
        eases = len(self.dial.eases)
        self.signal(True, False)
        self.assertEqual(len(self.dial.eases), eases)
        self.assertFalse(self.dial.visible)

    def test_disabling_hides_at_once(self):
        self.signal(True, True)
        self.signal(False, False)
        self.assertEqual(self.dial.eases[-1][0], 0)
        self.dial.finish()
        self.assertFalse(self.dial.visible)
        self.assertEqual(self.timers.pending, {})

    def test_fade_dims_after_a_moment_of_touching(self):
        self.look["visibility"] = "fade"
        self.signal(True, True)
        self.timers.advance(look.FADE_AFTER_MS - 1)
        self.assertEqual(self.dial.opacity, 255)
        self.timers.advance(1)
        self.assertEqual(self.dial.eases[-1], (89, look.FADE_SLOW_MS, look.ease_in_out_quad))
        # Lifting and touching again brings it back to full.
        self.signal(True, False)
        self.signal(True, True)
        self.assertEqual(self.dial.opacity, 255)

    def test_fade_rounds_like_javascript(self):
        self.look.update(visibility="fade", fadeOpacity=0.3)
        self.signal(True, True)
        self.timers.advance(look.FADE_AFTER_MS)
        self.assertEqual(self.dial.opacity, 77)  # Math.round(76.5)

    def test_pill_replaces_the_dial(self):
        self.look["visibility"] = "pill"
        self.signal(True, True)
        self.assertTrue(self.pill.visible)
        self.assertFalse(self.dial.visible)
        # A function with the full dial: the pill goes at once.
        self.look["visibility"] = "full"
        self.visibility.look_changed()
        self.assertFalse(self.pill.visible)
        self.assertEqual(self.pill.opacity, 0)
        self.assertTrue(self.dial.visible)

    def test_a_shown_actor_is_not_hidden_by_a_late_fade_out(self):
        self.signal(True, True)
        self.signal(False, False)
        self.signal(True, True)
        self.dial.finish()
        self.assertTrue(self.dial.visible)


class EasingTest(unittest.TestCase):
    def test_ends_and_middle(self):
        for easing in (look.ease_out_quad, look.ease_in_quad, look.ease_in_out_quad):
            self.assertEqual(easing(0), 0)
            self.assertEqual(easing(1), 1)
        self.assertEqual(look.ease_in_out_quad(0.5), 0.5)
        self.assertGreater(look.ease_out_quad(0.5), 0.5)
        self.assertLess(look.ease_in_quad(0.5), 0.5)


if __name__ == "__main__":
    unittest.main()
