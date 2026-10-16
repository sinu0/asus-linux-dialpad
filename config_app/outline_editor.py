"""Drawing a custom dial outline with the mouse.

The outline lives in a polar grid: its points sit at equal angles around
the centre (clockwise from the top) and each one only moves along its spoke,
towards or away from the centre. That keeps every shape around the centre,
so the dial stays usable, and makes squares, stars or flowers a matter of
dragging a few handles. Distances snap to SNAP of the full radius; with
mirroring on, the left half follows the right one.

The widget paints the live dial (overlay.painter) underneath, so the
editor shows exactly what the overlay will.
"""

from __future__ import annotations

import math
from typing import Callable

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gtk  # noqa: E402

from config.skins import OUTLINE_BOX, OUTLINE_RADIUS_MIN, mirror_index, outline_limit  # noqa: E402
from overlay.painter import OUTER_R, PAINTED_D, paint_dial  # noqa: E402

SNAP = 0.05
HANDLE_R = 7
GRAB_DISTANCE = 16

# Starting points for the editor: (label, points, smooth).
PRESETS = (
    ("Circle", [1.0] * 12, True),
    ("Square", [1.0, 1.41] * 4, False),
    ("Hexagon", [1.0] * 6, False),
    ("Star", [1.0, 0.62] * 5, False),
    ("Flower", [1.0, 0.84] * 6, True),
)


class OutlineEditor(Gtk.DrawingArea):
    """view_for() returns a painter DialView of the skin being edited;
    changed(points) runs after every drag step."""

    def __init__(self, view_for: Callable, outline: dict, changed: Callable[[list[float]], None],
                 size: int = 300, draw_icon: Callable | None = None):
        super().__init__()
        self._view_for = view_for
        self._draw_icon = draw_icon
        self._points = list(outline["points"])
        self._changed = changed
        self.mirror = True
        self._dragging = None
        self._hover = None
        self.set_content_width(size)
        self.set_content_height(size)
        self.set_halign(Gtk.Align.CENTER)
        self.set_draw_func(self._draw)

        drag = Gtk.GestureDrag.new()
        drag.connect("drag-begin", self._on_begin)
        drag.connect("drag-update", self._on_update)
        drag.connect("drag-end", self._on_end)
        self.add_controller(drag)
        motion = Gtk.EventControllerMotion.new()
        motion.connect("motion", self._on_motion)
        motion.connect("leave", lambda *_args: self._set_hover(None))
        self.add_controller(motion)
        self._drag_start = (0.0, 0.0)

    @property
    def points(self) -> list[float]:
        return list(self._points)

    def set_points(self, points: list[float]) -> None:
        self._points = list(points)
        self.queue_draw()

    # --- geometry -----------------------------------------------------------

    def _frame(self):
        """Centre and full outline radius of the dial in widget pixels."""
        width, height = self.get_width(), self.get_height()
        size = min(width, height)
        scale = size / PAINTED_D
        return width / 2, height / 2, OUTER_R * scale, (width - size) / 2, (height - size) / 2, size

    def _handle(self, index):
        cx, cy, radius, *_rest = self._frame()
        angle = index / len(self._points) * 2 * math.pi - math.pi / 2
        distance = radius * self._points[index]
        return cx + math.cos(angle) * distance, cy + math.sin(angle) * distance

    def _nearest(self, x, y):
        best, best_distance = None, GRAB_DISTANCE
        for index in range(len(self._points)):
            hx, hy = self._handle(index)
            distance = math.hypot(x - hx, y - hy)
            if distance <= best_distance:
                best, best_distance = index, distance
        return best

    # --- drawing ------------------------------------------------------------

    def _draw(self, _area, cr, _width, _height):
        cx, cy, radius, x, y, size = self._frame()
        paint_dial(cr, self._view_for(), x, y, size, draw_icon=self._draw_icon)

        # Polar grid: rings every 10 % from the smallest allowed distance,
        # and a spoke for every point.
        cr.set_line_width(1)
        cr.set_source_rgba(0.5, 0.65, 1.0, 0.35)
        ring = OUTLINE_RADIUS_MIN
        while ring <= 1.0001:
            cr.new_path()
            cr.arc(cx, cy, radius * ring, 0, 2 * math.pi)
            cr.stroke()
            ring += 0.1
        count = len(self._points)
        for index in range(count):
            angle = index / count * 2 * math.pi - math.pi / 2
            reach = radius * outline_limit(index, count)
            cr.move_to(cx + math.cos(angle) * radius * OUTLINE_RADIUS_MIN, cy + math.sin(angle) * radius * OUTLINE_RADIUS_MIN)
            cr.line_to(cx + math.cos(angle) * reach, cy + math.sin(angle) * reach)
        cr.stroke()
        # The square the outline has to stay in.
        box = radius * OUTLINE_BOX
        cr.set_dash([4, 4])
        cr.rectangle(cx - box, cy - box, 2 * box, 2 * box)
        cr.stroke()
        cr.set_dash([])

        for index in range(count):
            hx, hy = self._handle(index)
            active = index in (self._dragging, self._hover)
            cr.new_path()
            cr.arc(hx, hy, HANDLE_R + (2 if active else 0), 0, 2 * math.pi)
            cr.set_source_rgba(0.21, 0.52, 0.89, 1)
            cr.fill_preserve()
            cr.set_source_rgba(1, 1, 1, 1)
            cr.set_line_width(2)
            cr.stroke()

    # --- input --------------------------------------------------------------

    def _set_hover(self, index):
        if index != self._hover:
            self._hover = index
            self.set_cursor_from_name("grab" if index is not None else None)
            self.queue_draw()

    def _on_motion(self, _controller, x, y):
        if self._dragging is None:
            self._set_hover(self._nearest(x, y))

    def _on_begin(self, _gesture, x, y):
        self._dragging = self._nearest(x, y)
        self._drag_start = (x, y)
        if self._dragging is not None:
            self.set_cursor_from_name("grabbing")

    def _on_update(self, _gesture, dx, dy):
        index = self._dragging
        if index is None:
            return
        cx, cy, radius, *_rest = self._frame()
        x, y = self._drag_start[0] + dx, self._drag_start[1] + dy
        # Only the distance along the point's own spoke counts.
        angle = index / len(self._points) * 2 * math.pi - math.pi / 2
        along = (x - cx) * math.cos(angle) + (y - cy) * math.sin(angle)
        fraction = round(along / radius / SNAP) * SNAP
        fraction = round(max(OUTLINE_RADIUS_MIN, min(outline_limit(index, len(self._points)), fraction)), 2)
        if fraction == self._points[index]:
            return
        self._points[index] = fraction
        if self.mirror:
            self._points[mirror_index(index, len(self._points))] = fraction
        self._changed(self.points)
        self.queue_draw()

    def _on_end(self, _gesture, _dx, _dy):
        self._dragging = None
        self.set_cursor_from_name("grab" if self._hover is not None else None)
        self.queue_draw()


__all__ = ["OutlineEditor", "PRESETS"]
