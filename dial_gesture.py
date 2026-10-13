"""Hardware-independent DialPad gesture maths.

Kept free of evdev, D-Bus and display imports so it can be unit tested.
"""

from __future__ import annotations

import math
from typing import Optional, Tuple

DEFAULT_HYSTERESIS = 3
DEFAULT_DEBOUNCE_MS = 30
SCROLL_TRIGGER_DEGREES = 15


def touch_angle(dx: float, dy: float) -> float:
    """Return the clockwise angle in degrees, 0 at the top of the circle.

    Touchpad y grows downwards, so atan2 already runs clockwise.
    """
    return (math.atan2(dy, dx) * 180 / math.pi + 90) % 360


def slice_index(angle: float, count: int) -> int:
    """Return the radial menu slice under an angle for ``count`` slices."""
    if count <= 0:
        return 0
    return min(int((angle % 360) // (360 / count)), count - 1)


def scroll_acceleration_multiplier(degrees_per_second: float) -> int:
    """Keep slow DialPad scrolling precise while rewarding a quick spin."""
    if degrees_per_second < 55:
        return 1
    if degrees_per_second < 120:
        return 2
    if degrees_per_second < 240:
        return 3
    if degrees_per_second < 420:
        return 4
    return 6


class RotationTracker:
    """Accumulate finger rotation and report threshold crossings.

    ``reset()`` must be called whenever the finger touches down, lifts or
    leaves the ring; otherwise the first delta of the next touch is measured
    from the previous touch and fires a spurious action.
    """

    def __init__(self, hysteresis: float = DEFAULT_HYSTERESIS, debounce_ms: float = DEFAULT_DEBOUNCE_MS):
        self.hysteresis = hysteresis
        self.debounce_ms = debounce_ms
        self.last_trigger_time = 0.0
        self.reset()

    def reset(self) -> None:
        self.last_angle: Optional[float] = None
        self.start_angle: Optional[float] = None
        self.accumulator = 0.0
        self.rotation_start_time: Optional[float] = None

    @property
    def active(self) -> bool:
        return self.last_angle is not None

    def update(self, angle: float, now: float, threshold: float) -> Optional[Tuple[str, float]]:
        """Feed one frame's angle; return ``(direction, degrees_per_second)`` on a trigger."""
        if self.last_angle is None:
            self.last_angle = angle
            self.start_angle = angle
            self.accumulator = 0.0
            self.rotation_start_time = now
            return None

        delta = angle - self.last_angle
        if delta > 180:
            delta -= 360
        elif delta < -180:
            delta += 360

        # Movements below the hysteresis are measured against the same
        # reference angle, so slow rotation still accumulates.
        if abs(delta) >= self.hysteresis:
            self.accumulator += delta
            self.last_angle = angle

        if threshold <= 0 or abs(self.accumulator) < threshold:
            return None
        if (now - self.last_trigger_time) * 1000 < self.debounce_ms:
            return None

        direction = "clockwise" if self.accumulator > 0 else "counterclockwise"
        started = self.rotation_start_time if self.rotation_start_time is not None else now
        elapsed = max(now - started, 0.01)
        degrees_per_second = abs(self.accumulator) / elapsed

        self.last_trigger_time = now
        self.accumulator = 0.0
        self.rotation_start_time = now
        self.start_angle = angle
        return direction, degrees_per_second

    def progress(self, threshold: float) -> int:
        """Return the signed progress towards the threshold in percent."""
        if threshold <= 0:
            return 0
        return int(max(min(self.accumulator / threshold * 100, 100), -100))


def fit_circle(points):
    """Least-squares circle through ``points`` (Kåsa fit).

    Returns ``(cx, cy, radius, rms_error)`` or ``None`` when the points do
    not describe a circle (too few, or collinear).
    """
    count = len(points)
    if count < 3:
        return None
    mean_x = sum(x for x, _ in points) / count
    mean_y = sum(y for _, y in points) / count
    # Centred coordinates keep the normal equations well conditioned for
    # touchpad units in the thousands.
    suu = suv = svv = suuu = svvv = suvv = svuu = 0.0
    for x, y in points:
        u, v = x - mean_x, y - mean_y
        suu += u * u
        suv += u * v
        svv += v * v
        suuu += u * u * u
        svvv += v * v * v
        suvv += u * v * v
        svuu += v * u * u
    determinant = suu * svv - suv * suv
    if abs(determinant) < 1e-9:
        return None
    right_u = (suuu + suvv) / 2
    right_v = (svvv + svuu) / 2
    uc = (right_u * svv - right_v * suv) / determinant
    vc = (suu * right_v - suv * right_u) / determinant
    radius = math.sqrt(uc * uc + vc * vc + (suu + svv) / count)
    cx, cy = uc + mean_x, vc + mean_y
    rms = math.sqrt(sum((math.hypot(x - cx, y - cy) - radius) ** 2 for x, y in points) / count)
    return cx, cy, radius, rms


def angular_coverage(points, cx: float, cy: float) -> float:
    """Degrees of the circle covered by ``points`` (360 minus the largest gap)."""
    if len(points) < 2:
        return 0.0
    angles = sorted(touch_angle(x - cx, y - cy) for x, y in points)
    gaps = [b - a for a, b in zip(angles, angles[1:])]
    gaps.append(angles[0] + 360 - angles[-1])
    return 360.0 - max(gaps)


class CalibrationSession:
    """Guided calibration: trace the outer ring, then the centre button.

    Fed with raw touchpad coordinates by the driver; produces the dial
    geometry so new laptop models need no hand-measured layout.
    """

    STEPS = ("ring", "center")
    MIN_POINTS = 24
    MIN_COVERAGE = 270.0
    MAX_RELATIVE_RMS = 0.08
    TIMEOUT_SECONDS = 120.0

    def __init__(self, now: float):
        self.started = now
        self.step_index = 0
        self.points = []
        self.circles = {}
        self.message = "Trace the outer edge of the dial ring once, all the way round"
        self.error = ""
        self.done = False
        self.cancelled = False

    @property
    def step(self) -> str:
        return self.STEPS[min(self.step_index, len(self.STEPS) - 1)]

    @property
    def finished(self) -> bool:
        return self.done or self.cancelled

    def expired(self, now: float) -> bool:
        return now - self.started > self.TIMEOUT_SECONDS

    def add_point(self, x: float, y: float) -> bool:
        """Record a touch sample; return True when it was kept."""
        if self.finished:
            return False
        if self.points:
            last_x, last_y = self.points[-1]
            if abs(x - last_x) + abs(y - last_y) < 4:
                return False
        self.points.append((x, y))
        return True

    def coverage(self) -> float:
        fit = fit_circle(self.points)
        return angular_coverage(self.points, fit[0], fit[1]) if fit else 0.0

    def finish_stroke(self) -> None:
        """Evaluate the stroke that just ended with the finger lifting."""
        if self.finished:
            return
        points, self.points = self.points, []
        fit = fit_circle(points)
        if len(points) < self.MIN_POINTS or fit is None:
            self.error = "Too short — trace the whole circle in one movement"
            return
        cx, cy, radius, rms = fit
        if angular_coverage(points, cx, cy) < self.MIN_COVERAGE:
            self.error = "Only part of the circle was traced — go all the way round"
            return
        if rms > radius * self.MAX_RELATIVE_RMS:
            self.error = "The trace was not round enough — follow the printed edge"
            return
        if self.step == "center":
            ring = self.circles["ring"]
            if radius >= ring[2] * 0.85 or math.hypot(cx - ring[0], cy - ring[1]) > ring[2] * 0.25:
                self.error = "That was not the centre button — trace its edge inside the ring"
                return
        self.error = ""
        self.circles[self.step] = (cx, cy, radius)
        self.step_index += 1
        if self.step_index >= len(self.STEPS):
            self.done = True
            self.message = "Calibration finished"
        else:
            self.message = "Now trace the edge of the centre button"

    def result(self):
        """Geometry in touchpad units, or ``None`` until both steps passed."""
        if not self.done:
            return None
        ring_x, ring_y, ring_r = self.circles["ring"]
        _center_x, _center_y, center_r = self.circles["center"]
        return {
            "center_x": int(round(ring_x)),
            "center_y": int(round(ring_y)),
            "circle_diameter": int(round(ring_r * 2)),
            "center_button_diameter": int(round(center_r * 2)),
        }

    def state(self) -> dict:
        return {
            "active": not self.finished,
            "step": self.step,
            "step_index": self.step_index,
            "steps": len(self.STEPS),
            "points": len(self.points),
            "message": self.message,
            "error": self.error,
            "done": self.done,
            "cancelled": self.cancelled,
            "result": self.result(),
        }
