import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dial_gesture import (  # noqa: E402
    RotationTracker,
    scroll_acceleration_multiplier,
    slice_index,
    touch_angle,
)


def feed(tracker, angles, threshold, start=0.0, step=0.1):
    """Feed angles one frame at a time and collect triggers."""
    triggers = []
    for index, angle in enumerate(angles):
        result = tracker.update(angle % 360, start + index * step, threshold)
        if result is not None:
            triggers.append(result[0])
    return triggers


class TouchAngleTest(unittest.TestCase):
    def test_zero_is_top_and_runs_clockwise(self):
        # Touchpad y grows downwards.
        self.assertAlmostEqual(touch_angle(0, -10), 0)
        self.assertAlmostEqual(touch_angle(10, 0), 90)
        self.assertAlmostEqual(touch_angle(0, 10), 180)
        self.assertAlmostEqual(touch_angle(-10, 0), 270)


class SliceIndexTest(unittest.TestCase):
    def test_four_slices(self):
        self.assertEqual(slice_index(0, 4), 0)
        self.assertEqual(slice_index(89.9, 4), 0)
        self.assertEqual(slice_index(90, 4), 1)
        self.assertEqual(slice_index(359.9, 4), 3)

    def test_never_out_of_range(self):
        self.assertEqual(slice_index(360, 5), 0)
        self.assertEqual(slice_index(359.9999999, 7), 6)
        self.assertEqual(slice_index(10, 0), 0)


class RotationTrackerTest(unittest.TestCase):
    def test_first_frame_only_sets_reference(self):
        tracker = RotationTracker(hysteresis=3, debounce_ms=0)
        self.assertIsNone(tracker.update(120, 0.0, 90))
        self.assertEqual(tracker.accumulator, 0)

    def test_clockwise_and_counterclockwise(self):
        tracker = RotationTracker(hysteresis=3, debounce_ms=0)
        self.assertEqual(feed(tracker, range(0, 100, 10), 90), ["clockwise"])
        tracker.reset()
        self.assertEqual(feed(tracker, range(0, -100, -10), 90), ["counterclockwise"])

    def test_wraps_across_zero(self):
        tracker = RotationTracker(hysteresis=3, debounce_ms=0)
        # 330 -> 30 is +60 degrees, not -300.
        self.assertEqual(feed(tracker, [330, 350, 10, 30], 50), ["clockwise"])

    def test_hysteresis_filters_jitter(self):
        tracker = RotationTracker(hysteresis=5, debounce_ms=0)
        jitter = [100, 103, 98, 102, 99, 104, 97] * 10
        self.assertEqual(feed(tracker, jitter, 15), [])

    def test_slow_rotation_still_accumulates(self):
        tracker = RotationTracker(hysteresis=5, debounce_ms=0)
        # 2 degrees per frame is below the hysteresis but must add up.
        self.assertEqual(feed(tracker, range(0, 40, 2), 30), ["clockwise"])

    def test_one_trigger_per_threshold(self):
        tracker = RotationTracker(hysteresis=3, debounce_ms=0)
        self.assertEqual(feed(tracker, range(0, 361, 10), 90), ["clockwise"] * 4)

    def test_debounce(self):
        tracker = RotationTracker(hysteresis=3, debounce_ms=30)
        # All frames within 1 ms: only the first crossing may fire.
        self.assertEqual(feed(tracker, range(0, 200, 20), 40, start=100, step=0.0001), ["clockwise"])

    def test_reset_prevents_jump_between_touches(self):
        """Regression: a new touch must not be measured from the last one."""
        tracker = RotationTracker(hysteresis=3, debounce_ms=0)
        feed(tracker, [0, 10, 20], 90)
        tracker.reset()
        # The new touch lands 150 degrees away and stays still.
        self.assertEqual(feed(tracker, [170, 170, 171, 170], 90, start=5), [])

    def test_without_reset_a_new_touch_jumps(self):
        # Documents why the driver has to call reset() on every touch.
        tracker = RotationTracker(hysteresis=3, debounce_ms=0)
        feed(tracker, [0, 10, 20], 90)
        self.assertEqual(feed(tracker, [170], 90, start=5), ["clockwise"])

    def test_speed_is_reported(self):
        tracker = RotationTracker(hysteresis=3, debounce_ms=0)
        tracker.update(0, 0.0, 90)
        direction, degrees_per_second = tracker.update(90, 0.5, 90)
        self.assertEqual(direction, "clockwise")
        self.assertAlmostEqual(degrees_per_second, 180)

    def test_progress(self):
        tracker = RotationTracker(hysteresis=3, debounce_ms=0)
        feed(tracker, [0, 45], 180)
        self.assertEqual(tracker.progress(180), 25)
        self.assertEqual(tracker.progress(0), 0)
        tracker.reset()
        feed(tracker, [0, -90], 180)
        self.assertEqual(tracker.progress(180), -50)


class ScrollAccelerationTest(unittest.TestCase):
    def test_monotonic(self):
        speeds = [0, 54, 55, 119, 120, 239, 240, 419, 420, 2000]
        multipliers = [scroll_acceleration_multiplier(speed) for speed in speeds]
        self.assertEqual(multipliers, sorted(multipliers))
        self.assertEqual(multipliers[0], 1)
        self.assertEqual(multipliers[-1], 6)


class CalibrationTest(unittest.TestCase):
    @staticmethod
    def circle(cx, cy, r, start=0, sweep=360, count=80, noise=0.0):
        import math as m
        import random

        rng = random.Random(4)
        return [
            (cx + r * m.cos(m.radians(start + sweep * i / count)) + rng.uniform(-noise, noise),
             cy + r * m.sin(m.radians(start + sweep * i / count)) + rng.uniform(-noise, noise))
            for i in range(count)
        ]

    def test_fit_circle_recovers_geometry(self):
        from dial_gesture import fit_circle

        cx, cy, r, rms = fit_circle(self.circle(586, 573, 459, noise=6))
        self.assertAlmostEqual(cx, 586, delta=4)
        self.assertAlmostEqual(cy, 573, delta=4)
        self.assertAlmostEqual(r, 459, delta=4)
        self.assertLess(rms, 6)

    def test_fit_circle_rejects_degenerate_input(self):
        from dial_gesture import fit_circle

        self.assertIsNone(fit_circle([(0, 0), (1, 1)]))
        self.assertIsNone(fit_circle([(0, 0), (1, 1), (2, 2), (3, 3)]))

    def test_coverage_of_partial_arc(self):
        from dial_gesture import angular_coverage

        self.assertAlmostEqual(angular_coverage(self.circle(0, 0, 100, sweep=180, count=181), 0, 0), 180, delta=2)

    def test_guided_session_produces_layout(self):
        from dial_gesture import CalibrationSession

        session = CalibrationSession(now=0)
        for point in self.circle(770, 750, 700, count=120, noise=8):
            session.add_point(*point)
        session.finish_stroke()
        self.assertEqual(session.step, "center")
        for point in self.circle(772, 748, 125, count=60, noise=3):
            session.add_point(*point)
        session.finish_stroke()
        result = session.result()
        self.assertTrue(session.done)
        self.assertAlmostEqual(result["circle_diameter"], 1400, delta=12)
        self.assertAlmostEqual(result["center_button_diameter"], 250, delta=10)
        self.assertAlmostEqual(result["center_x"], 770, delta=6)

    def test_half_circle_is_rejected_and_step_repeats(self):
        from dial_gesture import CalibrationSession

        session = CalibrationSession(now=0)
        for point in self.circle(500, 500, 400, sweep=150, count=60):
            session.add_point(*point)
        session.finish_stroke()
        self.assertEqual(session.step, "ring")
        self.assertIn("part of the circle", session.error)

    def test_centre_must_lie_inside_the_ring(self):
        from dial_gesture import CalibrationSession

        session = CalibrationSession(now=0)
        for point in self.circle(500, 500, 400):
            session.add_point(*point)
        session.finish_stroke()
        for point in self.circle(900, 900, 100):
            session.add_point(*point)
        session.finish_stroke()
        self.assertFalse(session.done)
        self.assertIn("centre button", session.error)


if __name__ == "__main__":
    unittest.main()
